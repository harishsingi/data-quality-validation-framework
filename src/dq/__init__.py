"""Data quality validation framework.

Rule-driven validation: schema, null, duplicate, range, allowed-value,
and referential checks, with quarantine, freshness checks, and a
pass/fail report. Rules are config, not code; all data is synthetic.
"""

from .config import RuleConfig, load_config
from .errors import ConfigError, DataQualityError, InputError
from .freshness import FreshnessResult, check_freshness
from .report import ValidationReport
from .rules import Failure, RuleResult
from .validator import validate

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "ConfigError",
    "DataQualityError",
    "Failure",
    "FreshnessResult",
    "InputError",
    "RuleConfig",
    "RuleResult",
    "ValidationReport",
    "check_freshness",
    "load_config",
    "validate",
]
