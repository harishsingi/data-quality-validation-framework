"""Rule configuration: rules are config, not code.

A rule file is YAML validated into a frozen :class:`RuleConfig` before any
row is read, so a typo (unknown key, a range with ``low > high``, a rule on
a column that does not exist) fails fast with the key named, instead of
crashing mid-validation or silently running the wrong checks.

Example config (see ``rules/orders.yaml``)::

    required_columns: [id, customer_id, amount, updated_at]
    column_types:
      id: int
      amount: float
      updated_at: datetime
    not_null: [customer_id, amount]
    unique: [id]
    range:
      amount: [0, 10000]
    reference:
      customer_id:
        file: data/customers.csv
        column: customer_id
    expected_date: "2026-11-22"

Reference rules check a column against a master list, either inline
(``values: [...]``) or from a CSV file (``file: ...`` plus ``column: ...``).
A relative reference ``file`` is resolved against the config file's own
directory first, then the current working directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from .constants import SUPPORTED_COLUMN_TYPES
from .errors import ConfigError

# Every top-level key a config may contain. Anything else is a typo.
_KNOWN_KEYS = {
    "required_columns",
    "column_types",
    "not_null",
    "unique",
    "range",
    "allowed_values",
    "reference",
    "expected_date",
    "max_age_hours",
}


@dataclass(frozen=True)
class RangeRule:
    """Inclusive numeric bounds for one column."""

    column: str
    low: float
    high: float


@dataclass(frozen=True)
class ReferenceRule:
    """A column must match a master list of allowed values.

    Exactly one of ``values`` (inline list) or ``file`` (CSV file, resolved
    to an absolute path at load time) is set.
    """

    column: str
    values: frozenset[str] = frozenset()
    file: Path | None = None
    reference_column: str | None = None


@dataclass(frozen=True)
class RuleConfig:
    """A validated rule config. Immutable once loaded."""

    required_columns: tuple[str, ...]
    column_types: dict[str, str] = field(default_factory=dict)
    not_null: tuple[str, ...] = ()
    unique: tuple[str, ...] = ()
    ranges: tuple[RangeRule, ...] = ()
    allowed_values: dict[str, frozenset[str]] = field(default_factory=dict)
    references: tuple[ReferenceRule, ...] = ()
    expected_date: date | None = None
    max_age_hours: float | None = None


def _str_list(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{key!r} must be a list of column names, got {value!r}")
    if not value:
        raise ConfigError(f"{key!r} must not be empty")
    return tuple(value)


def _check_rule_columns(columns: tuple[str, ...], required: tuple[str, ...], key: str) -> None:
    unknown = [c for c in columns if c not in required]
    if unknown:
        raise ConfigError(
            f"{key!r} names columns not in required_columns: {unknown}"
        )


def _parse_expected_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ConfigError(
                f"expected_date must be YYYY-MM-DD, got {value!r}"
            ) from exc
    raise ConfigError(f"expected_date must be YYYY-MM-DD, got {value!r}")


def _resolve_reference_file(raw: object, config_dir: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError("reference 'file' must be a non-empty path string")
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate
    elif (config_dir / candidate).exists():
        resolved = config_dir / candidate
    elif (Path.cwd() / candidate).exists():
        resolved = Path.cwd() / candidate
    else:
        resolved = config_dir / candidate
    if not resolved.exists():
        raise ConfigError(
            f"reference file {raw!r} not found (looked in {config_dir} and {Path.cwd()})"
        )
    return resolved.resolve()


def _parse_reference(column: str, spec: object, config_dir: Path) -> ReferenceRule:
    if not isinstance(spec, dict):
        raise ConfigError(f"reference for {column!r} must be a mapping, got {spec!r}")
    has_values = "values" in spec
    has_file = "file" in spec
    if has_values == has_file:
        raise ConfigError(
            f"reference for {column!r} needs exactly one of 'values' or 'file'"
        )
    unknown = set(spec) - {"values", "file", "column"}
    if unknown:
        raise ConfigError(f"reference for {column!r} has unknown keys: {sorted(unknown)}")
    if has_values:
        values = spec["values"]
        if not isinstance(values, list) or not values:
            raise ConfigError(f"reference values for {column!r} must be a non-empty list")
        return ReferenceRule(column=column, values=frozenset(str(v) for v in values))
    reference_column = spec.get("column", column)
    if not isinstance(reference_column, str):
        raise ConfigError(f"reference 'column' for {column!r} must be a string")
    return ReferenceRule(
        column=column,
        file=_resolve_reference_file(spec["file"], config_dir),
        reference_column=reference_column,
    )


def load_config(path: str | Path) -> RuleConfig:
    """Load and validate a YAML rule config.

    Raises:
        ConfigError: file missing, not YAML, not a mapping, unknown key, or
            any section failing validation (message names the problem).
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read rules file {path}: {exc.strerror or exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"rules file {path} is not valid YAML: {exc}") from exc
    if raw is None:
        raise ConfigError(f"rules file {path} is empty")
    if not isinstance(raw, dict):
        raise ConfigError(f"rules file {path} must be a YAML mapping, got {type(raw).__name__}")
    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise ConfigError(f"rules file {path} has unknown keys: {sorted(unknown)}")

    required = _str_list(raw.get("required_columns"), "required_columns") if raw.get(
        "required_columns"
    ) is not None else None
    if required is None:
        raise ConfigError("'required_columns' is required and must be a non-empty list")

    column_types: dict[str, str] = {}
    raw_types = raw.get("column_types", {})
    if not isinstance(raw_types, dict):
        raise ConfigError("'column_types' must be a mapping of column to type")
    for column, type_name in raw_types.items():
        if column not in required:
            raise ConfigError(f"column_types names column {column!r} not in required_columns")
        if type_name not in SUPPORTED_COLUMN_TYPES:
            raise ConfigError(
                f"column_types[{column!r}] must be one of {SUPPORTED_COLUMN_TYPES}, "
                f"got {type_name!r}"
            )
        column_types[column] = type_name

    not_null = _str_list(raw["not_null"], "not_null") if "not_null" in raw else ()
    unique = _str_list(raw["unique"], "unique") if "unique" in raw else ()
    _check_rule_columns(not_null, required, "not_null")
    _check_rule_columns(unique, required, "unique")

    ranges: list[RangeRule] = []
    raw_ranges = raw.get("range", {})
    if not isinstance(raw_ranges, dict):
        raise ConfigError("'range' must be a mapping of column to [low, high]")
    for column, bounds in raw_ranges.items():
        if column not in required:
            raise ConfigError(f"range names column {column!r} not in required_columns")
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(isinstance(b, (int, float)) and not isinstance(b, bool) for b in bounds)
        ):
            raise ConfigError(f"range[{column!r}] must be [low, high] numbers, got {bounds!r}")
        low, high = float(bounds[0]), float(bounds[1])
        if low > high:
            raise ConfigError(f"range[{column!r}] has low {low} above high {high}")
        ranges.append(RangeRule(column=column, low=low, high=high))

    allowed_values: dict[str, frozenset[str]] = {}
    raw_allowed = raw.get("allowed_values", {})
    if not isinstance(raw_allowed, dict):
        raise ConfigError("'allowed_values' must be a mapping of column to a value list")
    for column, values in raw_allowed.items():
        if column not in required:
            raise ConfigError(f"allowed_values names column {column!r} not in required_columns")
        if not isinstance(values, list) or not values:
            raise ConfigError(f"allowed_values[{column!r}] must be a non-empty list")
        allowed_values[column] = frozenset(str(v) for v in values)

    references: list[ReferenceRule] = []
    raw_refs = raw.get("reference", {})
    if not isinstance(raw_refs, dict):
        raise ConfigError("'reference' must be a mapping of column to a reference spec")
    for column, spec in raw_refs.items():
        if column not in required:
            raise ConfigError(f"reference names column {column!r} not in required_columns")
        references.append(_parse_reference(column, spec, path.parent))

    expected_date = (
        _parse_expected_date(raw["expected_date"]) if "expected_date" in raw else None
    )
    max_age_hours = raw.get("max_age_hours")
    if max_age_hours is not None:
        if (
            not isinstance(max_age_hours, (int, float))
            or isinstance(max_age_hours, bool)
            or max_age_hours <= 0
        ):
            raise ConfigError(f"max_age_hours must be a positive number, got {max_age_hours!r}")
        max_age_hours = float(max_age_hours)

    return RuleConfig(
        required_columns=required,
        column_types=column_types,
        not_null=not_null,
        unique=unique,
        ranges=tuple(ranges),
        allowed_values=allowed_values,
        references=tuple(references),
        expected_date=expected_date,
        max_age_hours=max_age_hours,
    )
