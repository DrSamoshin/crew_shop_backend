# Stage 1: Builder - compile dependencies
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    curl libpq-dev gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Production-grade image: runtime deps only (no ruff / mypy / pytest). Dev work happens on
# the host (``uv sync`` without --no-dev); the container ships a minimal venv.
RUN uv sync --frozen --no-dev

# Stage 2: Runtime - minimal image
FROM python:3.13-slim

# Install only runtime dependencies (no gcc, no dev packages)
RUN apt-get update && apt-get install -y \
    libpq5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Add .venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
CMD ["python", "runner.py"]
