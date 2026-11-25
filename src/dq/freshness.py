"""Freshness check: is the newest data actually new?

Compares the latest timestamp in a batch against an expected date (or a
maximum age in hours). Timestamps are parsed as real datetimes, not
compared as strings: string comparison silently orders ``"2026-9-..."``
after ``"2026-11-..."`` and cannot tell a malformed timestamp from an old
one. Malformed timestamps are counted and reported instead of crashing
the check, and the latest *valid* timestamp is still evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .errors import DataQualityError


@dataclass(frozen=True)
class FreshnessResult:
    """Outcome of one freshness check."""

    passed: bool
    latest: datetime | None
    detail: str
    invalid_timestamps: int = 0

    def as_dict(self) -> dict:
        """JSON-serialisable form, for the validation report."""
        return {
            "passed": self.passed,
            "latest": self.latest.isoformat() if self.latest else None,
            "detail": self.detail,
            "invalid_timestamps": self.invalid_timestamps,
        }


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None if invalid.

    Accepts a trailing ``Z`` and date-only values (treated as midnight UTC).
    Naive timestamps are assumed to be UTC rather than rejected.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def latest_timestamp(
    rows: list[dict], column: str = "updated_at"
) -> tuple[datetime | None, int]:
    """Return ``(latest valid timestamp, count of invalid timestamps)``."""
    latest: datetime | None = None
    invalid = 0
    for row in rows:
        parsed = parse_timestamp(row.get(column))
        if parsed is None:
            if row.get(column) not in (None, ""):
                invalid += 1
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest, invalid


def check_freshness(
    rows: list[dict],
    column: str = "updated_at",
    expected_date: date | str | None = None,
    max_age_hours: float | None = None,
    now: datetime | None = None,
) -> FreshnessResult:
    """Pass when the latest timestamp is on/after ``expected_date`` (YYYY-MM-DD).

    With ``max_age_hours`` instead (or as well), pass when the latest
    timestamp is no older than that many hours before ``now`` (default: the
    current UTC time; pass ``now`` explicitly in tests for determinism).
    """
    if isinstance(expected_date, str):
        try:
            expected_date = date.fromisoformat(expected_date)
        except ValueError as exc:
            raise DataQualityError(
                f"expected_date must be YYYY-MM-DD, got {expected_date!r}"
            ) from exc
    latest, invalid = latest_timestamp(rows, column)
    if latest is None:
        return FreshnessResult(
            passed=False,
            latest=None,
            detail=f"no valid timestamps found in column {column!r}",
            invalid_timestamps=invalid,
        )
    if expected_date is not None and latest.date() < expected_date:
        return FreshnessResult(
            passed=False,
            latest=latest,
            detail=f"latest {latest.isoformat()} is before expected {expected_date}",
            invalid_timestamps=invalid,
        )
    if max_age_hours is not None:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        age = reference - latest
        if age > timedelta(hours=max_age_hours):
            return FreshnessResult(
                passed=False,
                latest=latest,
                detail=(
                    f"latest {latest.isoformat()} is {age} old, "
                    f"older than max age {max_age_hours}h"
                ),
                invalid_timestamps=invalid,
            )
    return FreshnessResult(
        passed=True,
        latest=latest,
        detail=f"latest {latest.isoformat()}",
        invalid_timestamps=invalid,
    )
