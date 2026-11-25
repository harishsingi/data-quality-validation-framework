"""Logging setup.

One place configures the format for the whole framework. Diagnostics go to
stderr so the CLI can still print the JSON report on stdout.
"""

import logging
import sys

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once; repeated calls are harmless."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=DEFAULT_LOG_FORMAT,
        stream=sys.stderr,
    )
