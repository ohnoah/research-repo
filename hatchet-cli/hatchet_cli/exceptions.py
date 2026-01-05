"""
Hatchet CLI Exceptions - Custom exceptions for error handling.

This module provides specific exception types for different error scenarios
when interacting with the Hatchet API.
"""


class HatchetCLIError(Exception):
    """Base exception for all Hatchet CLI errors."""

    pass


class HatchetConfigurationError(HatchetCLIError):
    """Raised when the CLI is misconfigured (missing credentials, invalid settings)."""

    pass


class HatchetAPIError(HatchetCLIError):
    """
    Raised when the Hatchet API returns an error response.

    Attributes:
        message: Error message from the API
        status_code: HTTP status code of the response
    """

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        if self.status_code:
            return f"[HTTP {self.status_code}] {self.message}"
        return self.message


class HatchetAuthenticationError(HatchetAPIError):
    """Raised when authentication fails (invalid or expired token)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class HatchetNotFoundError(HatchetAPIError):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class HatchetRateLimitError(HatchetAPIError):
    """Raised when rate limits are exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429)


class HatchetValidationError(HatchetCLIError):
    """Raised when input validation fails."""

    pass
