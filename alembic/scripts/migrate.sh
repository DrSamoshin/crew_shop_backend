#!/bin/bash

# Universal migration script for Cloud SQL
# This script connects to Cloud SQL via cloud_sql_proxy and applies migrations
# Usage: ./migrate.sh <environment> [alembic_command]
# Example: ./migrate.sh stage upgrade head
# Example: ./migrate.sh prod current
# Example: ./migrate.sh stage reset          # Drop all tables + reapply migrations (stage only)

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALEMBIC_DIR="$(dirname "${SCRIPT_DIR}")"
PROJECT_ROOT="$(dirname "${ALEMBIC_DIR}")"

# Check arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Environment argument required${NC}"
    echo "Usage: $0 <environment> [alembic_command]"
    echo "Example: $0 stage upgrade head"
    echo "Example: $0 prod current"
    exit 1
fi

ENVIRONMENT=$1
shift  # Remove first argument, rest are alembic commands

# Handle reset command (stage only)
if [ "$1" = "reset" ]; then
    if [ "${ENVIRONMENT}" != "stage" ]; then
        echo -e "${RED}Error: reset command is only allowed for stage environment${NC}"
        exit 1
    fi
    MIGRATION_CMD="reset"
else
    # Get migration command (default: upgrade head)
    MIGRATION_CMD="${@:-upgrade head}"
fi

# Load environment file
ENV_FILE="${SCRIPT_DIR}/.env.${ENVIRONMENT}"

if [ ! -f "${ENV_FILE}" ]; then
    echo -e "${RED}Error: Environment file not found: ${ENV_FILE}${NC}"
    echo "Available environments: stage, prod"
    exit 1
fi

echo -e "${YELLOW}Loading configuration from ${ENV_FILE}${NC}"
source "${ENV_FILE}"

# Validate required variables
if [ -z "${DATABASE_HOST}" ] || [ -z "${DATABASE_USER}" ] || [ -z "${DATABASE_PASSWORD}" ] || [ -z "${DATABASE_NAME}" ]; then
    echo -e "${RED}Error: Missing required variables in ${ENV_FILE}${NC}"
    echo "Required: DATABASE_HOST, DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME"
    exit 1
fi

# Default proxy port if not set
PROXY_PORT=${PROXY_PORT:-5433}

# Check if cloud_sql_proxy is installed
if ! command -v cloud-sql-proxy &> /dev/null; then
    echo -e "${RED}Error: cloud_sql_proxy is not installed or not in PATH${NC}"
    echo "Install it from: https://cloud.google.com/sql/docs/mysql/sql-proxy"
    exit 1
fi

echo -e "${YELLOW}Starting Cloud SQL Proxy for ${ENVIRONMENT}...${NC}"

# Create log file for proxy output
PROXY_LOG="/tmp/migrate_${ENVIRONMENT}_proxy.log"
rm -f ${PROXY_LOG}

# Start cloud_sql_proxy in background
cloud-sql-proxy --port=${PROXY_PORT} ${DATABASE_HOST} > ${PROXY_LOG} 2>&1 &
PROXY_PID=$!

# Save PID for cleanup
PID_FILE="/tmp/migrate_${ENVIRONMENT}_proxy.pid"
echo $PROXY_PID > ${PID_FILE}

# Cleanup function
cleanup() {
    echo -e "${YELLOW}Stopping Cloud SQL Proxy...${NC}"
    if [ -f ${PID_FILE} ]; then
        kill $(cat ${PID_FILE}) 2>/dev/null || true
        rm ${PID_FILE}
    fi
    rm -f ${PROXY_LOG}
}

# Trap cleanup on script exit
trap cleanup EXIT INT TERM

# Function to wait for proxy to be ready
wait_for_proxy() {
    local max_attempts=30
    local attempt=0

    echo -e "${YELLOW}Waiting for proxy to be ready...${NC}"

    while [ $attempt -lt $max_attempts ]; do
        # Check if proxy log contains ready message
        if grep -q "ready for new connections" ${PROXY_LOG} 2>/dev/null; then
            echo -e "${GREEN}Cloud SQL Proxy is ready on 127.0.0.1:${PROXY_PORT}${NC}"
            return 0
        fi

        # Check if proxy process is still running
        if ! kill -0 $PROXY_PID 2>/dev/null; then
            echo -e "${RED}Error: Cloud SQL Proxy process died${NC}"
            echo -e "${RED}Last logs:${NC}"
            tail -10 ${PROXY_LOG}
            return 1
        fi

        attempt=$((attempt + 1))
        sleep 0.5
    done

    echo -e "${RED}Error: Timeout waiting for Cloud SQL Proxy${NC}"
    echo -e "${RED}Proxy logs:${NC}"
    cat ${PROXY_LOG}
    return 1
}

# Wait for proxy to be ready
if ! wait_for_proxy; then
    exit 1
fi

# Build database URL
DATABASE_URL="postgresql+asyncpg://${DATABASE_USER}:${DATABASE_PASSWORD}@localhost:${PROXY_PORT}/${DATABASE_NAME}"

# Handle reset: drop schema via psql + upgrade head
if [ "${MIGRATION_CMD}" = "reset" ]; then
    echo -e "${RED}WARNING: This will drop ALL tables in the ${ENVIRONMENT} database (${DATABASE_NAME})${NC}"
    read -p "Type 'stage' to confirm: " CONFIRM
    if [ "${CONFIRM}" != "stage" ]; then
        echo -e "${RED}Aborted${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Dropping all tables on ${ENVIRONMENT}...${NC}"
    PGPASSWORD="${DATABASE_PASSWORD}" psql -h localhost -p ${PROXY_PORT} -U ${DATABASE_USER} -d ${DATABASE_NAME} -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

    cd "${PROJECT_ROOT}"

    echo -e "${YELLOW}Applying all migrations on ${ENVIRONMENT}...${NC}"
    DATABASE_URL="${DATABASE_URL}" uv run alembic upgrade head

    echo -e "${GREEN}Database reset completed on ${ENVIRONMENT}!${NC}"
    exit 0
fi

# Detect command type for better messaging
FIRST_CMD=$(echo ${MIGRATION_CMD} | awk '{print $1}')
case ${FIRST_CMD} in
    current)
        ACTION_MSG="Checking current migration version"
        SUCCESS_MSG="Current version retrieved successfully"
        ;;
    history)
        ACTION_MSG="Fetching migration history"
        SUCCESS_MSG="History retrieved successfully"
        ;;
    downgrade)
        ACTION_MSG="Downgrading migrations"
        SUCCESS_MSG="Downgrade completed successfully"
        ;;
    upgrade)
        ACTION_MSG="Applying migrations"
        SUCCESS_MSG="Migrations applied successfully"
        ;;
    *)
        ACTION_MSG="Running alembic command"
        SUCCESS_MSG="Command completed successfully"
        ;;
esac

# Run migrations from project root
echo -e "${YELLOW}${ACTION_MSG} on ${ENVIRONMENT}: alembic ${MIGRATION_CMD}${NC}"
cd "${PROJECT_ROOT}"
DATABASE_URL="${DATABASE_URL}" uv run alembic ${MIGRATION_CMD}

echo -e "${GREEN}${SUCCESS_MSG} on ${ENVIRONMENT}!${NC}"
