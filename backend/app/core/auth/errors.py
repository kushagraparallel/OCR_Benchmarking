"""Domain errors raised by authentication services."""


class AuthenticationError(Exception):
    """Base class for expected authentication failures."""


class InvalidCredentialsError(AuthenticationError):
    """Credentials are invalid or the account cannot authenticate."""


class EmailAlreadyRegisteredError(AuthenticationError):
    """An account already exists for the normalized email address."""


class InvalidRefreshTokenError(AuthenticationError):
    """The refresh token is missing, invalid, expired, or revoked."""


class SessionNotFoundError(AuthenticationError):
    """The requested session is not owned by the current user."""
