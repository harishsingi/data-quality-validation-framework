"""Row-level rule checks.

Each check is a pure function: rows in, a :class:`RuleResult` out. Checks
never raise on bad data; a value that cannot be parsed is a failed row,
not an exception. Ownership is split so a rule can be tested alone:

- ``not_null`` owns empty values; other checks skip empty values so one
  bad cell produces one failure, not one per rule.
- ``unique`` skips empty values for the same reason (a missing id is a
  null failure, not a duplicate).
- ``range`` skips empty values; a non-numeric value fails as "not numeric".

``validate`` is kept as a compatibility wrapper around
:func:`src.dq.validator.validate`; new code should use the validator,
which returns a full :class:`~src.dq.report.ValidationReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .constants import BATCH_RECORD_ID, DEFAULT_ID_COLUMN, MAX_FAILURES_PER_RULE


@dataclass(frozen=True)
class Failure:
    """One row failing one rule, with the reason attached.

    ``row_index`` is the row's position in the validated input (0-based).
    It is what ties a failure to its exact row: two rows can share an id
    (a duplicate), so the id alone cannot say which one failed which rule.
    """

    record_id: str
    rule: str
    detail: str
    row_index: int | None = None


@dataclass
class RuleResult:
    """The outcome of one rule over all rows."""

    rule: str
    passed: int = 0
    failed: int = 0
    failures: list[Failure] = field(default_factory=list)

    def record_failure(
        self, record_id: str, detail: str, row_index: int | None = None
    ) -> None:
        """Count a failure, keeping at most MAX_FAILURES_PER_RULE details."""
        self.failed += 1
        if len(self.failures) < MAX_FAILURES_PER_RULE:
            self.failures.append(Failure(record_id, self.rule, detail, row_index))

    @property
    def total(self) -> int:
        """Rows (or columns, for schema) this rule evaluated."""
        return self.passed + self.failed

    def as_dict(self) -> dict:
        """JSON-serialisable form, for the validation report."""
        return {
            "rule": self.rule,
            "passed": self.passed,
            "failed": self.failed,
            "failures": [
                {
                    "record_id": f.record_id,
                    "rule": f.rule,
                    "detail": f.detail,
                    **({"row_index": f.row_index} if f.row_index is not None else {}),
                }
                for f in self.failures
            ],
        }


def record_id_of(row: dict, id_column: str = DEFAULT_ID_COLUMN) -> str:
    """The id used to trace a failure back to its row."""
    return str(row.get(id_column, BATCH_RECORD_ID))


def is_null(value: object) -> bool:
    """Null means missing or blank (whitespace-only counts as blank)."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_typed(raw: str, type_name: str) -> bool:
    """True when ``raw`` parses as ``type_name`` ("int", "float", "str", "datetime")."""
    value = raw.strip()
    if type_name == "str":
        return True
    if type_name == "int":
        try:
            int(value)
        except ValueError:
            return False
        return True
    if type_name == "float":
        try:
            float(value)
        except ValueError:
            return False
        return True
    if type_name == "datetime":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    return False


def check_schema(rows: list[dict], required: list[str] | tuple[str, ...]) -> RuleResult:
    """Fail the whole batch when a required column is missing or there are no rows.

    ``passed`` counts required columns present (not rows): a schema result
    of 4 passed / 0 failed means all 4 required columns were found.
    """
    result = RuleResult(rule="schema")
    if not rows:
        result.record_failure(BATCH_RECORD_ID, "no rows")
        return result
    missing = [c for c in required if c not in rows[0]]
    if missing:
        result.record_failure(BATCH_RECORD_ID, f"missing columns: {missing}")
    else:
        result.passed += len(required)
    return result


def check_column_types(
    rows: list[dict], column_types: dict[str, str]
) -> list[RuleResult]:
    """One result per typed column: every non-empty value must parse as its type."""
    results: list[RuleResult] = []
    for column, type_name in column_types.items():
        result = RuleResult(rule=f"schema:type:{column}")
        for index, row in enumerate(rows):
            value = row.get(column)
            if is_null(value):
                continue  # not_null owns empty values
            if _parse_typed(str(value), type_name):
                result.passed += 1
            else:
                result.record_failure(
                    record_id_of(row),
                    f"{column}={value!r} is not a {type_name}",
                    row_index=index,
                )
        results.append(result)
    return results


def check_not_null(rows: list[dict], column: str) -> RuleResult:
    """Fail rows where ``column`` is missing or blank."""
    result = RuleResult(rule=f"not_null:{column}")
    for index, row in enumerate(rows):
        if is_null(row.get(column)):
            result.record_failure(record_id_of(row), f"{column} is null", row_index=index)
        else:
            result.passed += 1
    return result


def check_unique(rows: list[dict], column: str) -> RuleResult:
    """Fail every repeat occurrence of a value in ``column`` (first one passes)."""
    result = RuleResult(rule=f"unique:{column}")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        value = row.get(column)
        if is_null(value):
            continue  # not_null owns empty values
        key = str(value)
        if key in seen:
            result.record_failure(
                record_id_of(row), f"duplicate {column}={value}", row_index=index
            )
        else:
            seen.add(key)
            result.passed += 1
    return result


def check_range(rows: list[dict], column: str, low: float, high: float) -> RuleResult:
    """Fail rows where ``column`` is non-numeric or outside [low, high] (inclusive)."""
    result = RuleResult(rule=f"range:{column}[{low:g},{high:g}]")
    for index, row in enumerate(rows):
        value = row.get(column)
        if is_null(value):
            continue  # not_null owns empty values
        try:
            numeric = float(str(value))
        except (TypeError, ValueError):
            result.record_failure(
                record_id_of(row), f"{column} is not numeric", row_index=index
            )
            continue
        if low <= numeric <= high:
            result.passed += 1
        else:
            result.record_failure(
                record_id_of(row), f"{column}={numeric:g} out of range", row_index=index
            )
    return result


def check_allowed_values(
    rows: list[dict], column: str, allowed: frozenset[str] | set[str]
) -> RuleResult:
    """Fail rows where ``column`` is not one of the allowed values."""
    result = RuleResult(rule=f"allowed_values:{column}")
    for index, row in enumerate(rows):
        value = row.get(column)
        if is_null(value):
            continue  # not_null owns empty values
        if str(value) in allowed:
            result.passed += 1
        else:
            result.record_failure(
                record_id_of(row),
                f"{column}={value!r} is not an allowed value",
                row_index=index,
            )
    return result


def check_reference(
    rows: list[dict], column: str, allowed_values: frozenset[str] | set[str]
) -> RuleResult:
    """Referential check: fail rows whose ``column`` has no match in the master list."""
    result = RuleResult(rule=f"reference:{column}")
    for index, row in enumerate(rows):
        value = row.get(column)
        if is_null(value):
            continue  # not_null owns empty values
        if str(value).strip() in allowed_values:
            result.passed += 1
        else:
            result.record_failure(
                record_id_of(row),
                f"{column}={value!r} has no match in the reference data",
                row_index=index,
            )
    return result


def validate(
    rows: list[dict], config
) -> tuple[list[RuleResult], list[str]]:
    """Compatibility wrapper around :func:`src.dq.validator.validate`.

    Returns ``(results, quarantined_ids)`` as the original API did.
    Prefer :func:`src.dq.validator.validate`, which returns a full report.
    """
    from .validator import validate as _validate

    report = _validate(rows, config)
    return report.results, report.quarantined_ids
