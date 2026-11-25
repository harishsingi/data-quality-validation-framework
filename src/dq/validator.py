"""Validator: run every rule in a config over a dataset.

Orchestration only; the individual checks live in
:mod:`src.dq.rules`. A schema failure is batch-level (its failure id is
``"batch"``), so it never quarantines a row by itself: only ids that
actually occur in the input rows can be quarantined.
"""

from __future__ import annotations

import logging

from .config import RuleConfig
from .constants import BATCH_RECORD_ID, DEFAULT_ID_COLUMN
from .io import load_reference_values
from .report import ValidationReport
from .rules import (
    check_allowed_values,
    check_column_types,
    check_not_null,
    check_range,
    check_reference,
    check_schema,
    check_unique,
)

logger = logging.getLogger(__name__)


def _resolve_reference_values(config: RuleConfig) -> dict[str, frozenset[str]]:
    """Resolve every reference rule to its allowed-value set."""
    resolved: dict[str, frozenset[str]] = {}
    for rule in config.references:
        if rule.values:
            resolved[rule.column] = rule.values
        elif rule.file is not None:
            resolved[rule.column] = load_reference_values(
                rule.file, rule.reference_column or rule.column
            )
    return resolved


def validate(
    rows: list[dict],
    config: RuleConfig,
    reference_values: dict[str, frozenset[str]] | None = None,
    id_column: str = DEFAULT_ID_COLUMN,
) -> ValidationReport:
    """Run every rule in ``config`` over ``rows`` and build the report.

    ``reference_values`` lets callers (mainly tests) supply a master list
    without a file; otherwise file-based references are loaded here.
    """
    results = [check_schema(rows, config.required_columns)]
    results.extend(check_column_types(rows, config.column_types))
    for column in config.not_null:
        results.append(check_not_null(rows, column))
    for column in config.unique:
        results.append(check_unique(rows, column))
    for rule in config.ranges:
        results.append(check_range(rows, rule.column, rule.low, rule.high))
    for column, allowed in config.allowed_values.items():
        results.append(check_allowed_values(rows, column, allowed))
    if config.references:
        resolved = reference_values or _resolve_reference_values(config)
        for rule in config.references:
            results.append(
                check_reference(rows, rule.column, resolved[rule.column])
            )

    row_ids = {str(row.get(id_column, "")) for row in rows}
    quarantined_ids = sorted(
        {
            failure.record_id
            for result in results
            for failure in result.failures
            if failure.record_id in row_ids
            and failure.record_id != BATCH_RECORD_ID
        }
    )
    quarantined_rows = sum(
        1 for row in rows if str(row.get(id_column, "")) in set(quarantined_ids)
    )
    for result in results:
        logger.debug(
            "%s: %d passed, %d failed", result.rule, result.passed, result.failed
        )
    logger.info(
        "validated %d rows: %d clean, %d quarantined (%d distinct ids)",
        len(rows),
        len(rows) - quarantined_rows,
        quarantined_rows,
        len(quarantined_ids),
    )
    return ValidationReport(
        rows_in=len(rows),
        results=results,
        quarantined_ids=quarantined_ids,
        quarantined_rows=quarantined_rows,
    )
