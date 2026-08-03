"""统一业务错误码。"""

from __future__ import annotations


class AppError(Exception):
    """可映射到统一错误体的业务异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "unauthorized") -> None:
        super().__init__("UNAUTHORIZED", message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "forbidden") -> None:
        super().__init__("FORBIDDEN", message, status_code=403)


class NotFoundError(AppError):
    def __init__(self, message: str = "not found") -> None:
        super().__init__("NOT_FOUND", message, status_code=404)


class ValidationAppError(AppError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, status_code=422, details=details)
