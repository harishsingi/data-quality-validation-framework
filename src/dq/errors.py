"""Errors for the data quality validation framework.

All recoverable, user-facing failures raise :class:`DataQualityError` (or a
subclass) so the CLI can report them cleanly and exit non-zero instead of
printing a traceback for a bad config or a missing file.
"""


class DataQualityError(Exception):
    """Base class for all framework errors."""


class ConfigError(DataQualityError):
    """Raised when a rule config file is missing, malformed, or invalid."""


class InputError(DataQualityError):
    """Raised when an input dataset (or reference file) cannot be read."""
