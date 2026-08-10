"""Fail-closed domain errors mapped by the API boundary."""

from __future__ import annotations


class StockoutOpsError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AuthenticationError(StockoutOpsError):
    def __init__(self, message: str = "Missing or invalid bearer token") -> None:
        super().__init__("UNAUTHENTICATED", message, 401)


class AuthorizationError(StockoutOpsError):
    def __init__(self, message: str = "Operation is not permitted") -> None:
        super().__init__("FORBIDDEN", message, 403)


class NotFoundError(StockoutOpsError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "Investigation not found", 404)


class ConflictError(StockoutOpsError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


class ValidationError(StockoutOpsError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 422)


class ConfigurationError(RuntimeError):
    pass
