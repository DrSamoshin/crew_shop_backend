"""Gunicorn configuration for prod/stage environments."""

from src.api.core.configs import settings
from src.api.core.logging_config import get_logging_config

logconfig_dict = get_logging_config(settings.log_level)
