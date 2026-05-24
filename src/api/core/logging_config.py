"""Centralized logging configuration.

JSON structured logging via dictConfig, suitable for cloud log aggregation.
"""

from typing import Any


def get_logging_config(log_level: str = "INFO") -> dict[str, Any]:
    """Return a Python logging dictConfig with JSON formatting for all environments."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "default": {
                "formatter": "json",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": log_level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": log_level, "propagate": False},
            "src": {"handlers": ["default"], "level": log_level, "propagate": False},
            "sqlalchemy.engine": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
        },
        "root": {"handlers": ["default"], "level": "WARNING"},
    }
