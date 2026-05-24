"""Application exceptions."""


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)
