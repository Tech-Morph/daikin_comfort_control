"""Exceptions for Daikin Comfort Control."""


class DaikinAuthError(Exception):
    """Raised when authentication fails."""


class DaikinApiError(Exception):
    """Raised when API call fails."""


class DaikinTokenExpiredError(DaikinApiError):
    """Raised when the access token has expired."""
