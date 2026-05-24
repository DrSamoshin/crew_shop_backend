"""Environment bootstrap.

Loads the .env file based on the ENV variable.
Must be imported before any Settings class is instantiated.
"""

import os

from dotenv import load_dotenv


def _load_env() -> None:
    """Load environment variables from a .env file when not in a cloud environment."""
    env = os.getenv("ENV", "dev")
    if env not in ("stage", "prod"):
        load_dotenv(f".env.{env}")


_load_env()
