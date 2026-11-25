"""Quarantine: failed records never reach gold, with the reason attached.

Idempotency note: both writers are deterministic overwrites, not appends.
Re-running a validation on the same input produces byte-identical files,
and re-running after a fix replaces the old quarantine instead of
double-counting it. A record that fails several rules appears once, with
every failure reason joined, so the quarantined row count matches the
number of bad rows (the original writer kept only the last reason and the
caller had to reconcile ids against rows).
"""

from __future__ import annotations

from pathlib import Path

from .constants import DEFAULT_ID_COLUMN
from .errors import InputError
from .io import write_csv
from .rules import Failure


def _reasons_by_row(
    rows: list[dict], failures: list[Failure], id_column: str
) -> dict[int, list[str]]:
    """Map each failing row's index to its reasons, in first-seen order.

    Failures carry the row index they came from, so two rows sharing an id
    (a duplicate) get only their own reasons. Failures built without an
    index (for example by a caller constructing ``Failure`` directly) fall
    back to matching by record id.
    """
    by_index: dict[int, list[str]] = {}
    by_id: dict[str, list[str]] = {}
    for failure in failures:
        reason = f"{failure.rule}: {failure.detail}"
        target = (
            by_index.setdefault(failure.row_index, [])
            if failure.row_index is not None
            else by_id.setdefault(failure.record_id, [])
        )
        if reason not in target:
            target.append(reason)
    result: dict[int, list[str]] = {}
    for index, row in enumerate(rows):
        reasons = by_index.get(index)
        if reasons is None:
            reasons = by_id.get(str(row.get(id_column, "")), [])
        if reasons:
            result[index] = reasons
    return result


def failure_reasons(failures: list[Failure]) -> dict[str, list[str]]:
    """Group failure reasons by record id, in first-seen order, de-duplicated.

    Kept for callers that only have ids; :func:`write_quarantine` itself
    groups by row (see :func:`_reasons_by_row`) so duplicate ids do not
    share reasons.
    """
    reasons: dict[str, list[str]] = {}
    for failure in failures:
        entry = reasons.setdefault(failure.record_id, [])
        reason = f"{failure.rule}: {failure.detail}"
        if reason not in entry:
            entry.append(reason)
    return reasons


def write_quarantine(
    rows: list[dict],
    failures: list[Failure],
    out_path: str | Path,
    id_column: str = DEFAULT_ID_COLUMN,
) -> int:
    """Write every row that failed at least one rule, with all its reasons.

    Returns the number of quarantined rows (0 when nothing failed). The
    output keeps the input row order and appends a ``quarantine_reason``
    column. A duplicated id quarantines every row carrying it, but each
    row lists only the rules it itself failed.
    """
    reasons = _reasons_by_row(rows, failures, id_column)
    if not rows:
        return write_csv([], out_path, [id_column, "quarantine_reason"])
    fieldnames = list(rows[0].keys()) + ["quarantine_reason"]
    quarantined = [
        {**row, "quarantine_reason": "; ".join(reasons[index])}
        for index, row in enumerate(rows)
        if index in reasons
    ]
    return write_csv(quarantined, out_path, fieldnames)


def write_clean(
    rows: list[dict],
    quarantined_ids: list[str] | set[str],
    out_path: str | Path,
    fieldnames: list[str] | None = None,
    id_column: str = DEFAULT_ID_COLUMN,
) -> int:
    """Write the rows that passed every rule: the only rows allowed into gold.

    Returns the number of clean rows written. ``fieldnames`` is required
    when ``rows`` is empty (there is no row to infer the header from).
    """
    quarantined = set(quarantined_ids)
    clean = [row for row in rows if str(row.get(id_column, "")) not in quarantined]
    if fieldnames is None:
        if not rows:
            raise InputError(
                "cannot write clean output: no rows and no fieldnames given"
            )
        fieldnames = list(rows[0].keys())
    return write_csv(clean, out_path, fieldnames)
