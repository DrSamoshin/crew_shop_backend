import os

import uvicorn

from src.api.core.configs import settings
from src.api.core.logging_config import get_logging_config


def run_api() -> None:
    if settings.env in ("prod", "stage"):
        workers = settings.workers or ((os.cpu_count() or 1) * 2 + 1)
        os.execvp(
            "gunicorn",
            [
                "gunicorn",
                "src:fastapi_app",
                "--workers",
                str(workers),
                "--worker-class",
                "uvicorn.workers.UvicornWorker",
                "--bind",
                f"{settings.app_host}:{settings.app_port}",
                "--access-logfile",
                "-",
                "--config",
                "gunicorn.conf.py",
            ],
        )
    else:
        uvicorn.run(
            "src:fastapi_app",
            host=settings.app_host,
            port=settings.app_port,
            reload=settings.is_dev,
            log_config=get_logging_config(settings.log_level),
            access_log=False,
        )


if __name__ == "__main__":
    run_api()
