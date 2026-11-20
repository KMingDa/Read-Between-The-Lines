"""Expected failures raised by services. The API layer maps each type to an HTTP status."""


class AppError(Exception):
    """An expected failure whose message is safe to show to API clients."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(AppError):
    """The input passed schema validation but breaks a business rule."""


class ConflictError(AppError):
    """The request clashes with data that already exists."""


class AuthenticationError(AppError):
    """Credentials or token are missing, wrong, expired or no longer valid."""


class NotFoundError(AppError):
    """The resource does not exist or belongs to another user; the two look the same on purpose."""


class PayloadTooLargeError(AppError):
    """An upload is larger than allowed."""
