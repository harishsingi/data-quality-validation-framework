"""Validation report: rows in, rows out, rejected counts, per-rule results.

One object carries everything a run produced, so the CLI, the tests, and
any future alerting all read the same numbers instead of each recomputing
them from printed lines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .freshness import FreshnessResult
from .rules import RuleResult


@dataclass
class ValidationReport:
    """The complete outcome of validating one dataset against one config."""

    rows_in: int
    results: list[RuleResult] = field(default_factory=list)
    quarantined_ids: list[str] = field(default_factory=list)
    quarantined_rows: int = 0
    freshness: FreshnessResult | None = None

    @property
    def rows_out(self) -> int:
        """Clean rows: the only rows allowed into gold."""
        return self.rows_in - self.quarantined_rows

    @property
    def rejected_rows(self) -> int:
        """Rows quarantined (same count as ``quarantined_rows``; named for logs)."""
        return self.quarantined_rows

    @property
    def passed(self) -> bool:
        """True only when every rule passed and freshness passed (if checked)."""
        rules_ok = all(result.failed == 0 for result in self.results)
        freshness_ok = self.freshness.passed if self.freshness is not None else True
        return rules_ok and freshness_ok

    def attach_freshness(self, freshness: FreshnessResult) -> None:
        """Attach the freshness result; ``passed`` reflects it afterwards."""
        self.freshness = freshness

    def to_dict(self) -> dict:
        """JSON-serialisable form."""
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "quarantined_rows": self.quarantined_rows,
            "quarantined_ids": self.quarantined_ids,
            "passed": self.passed,
            "freshness": self.freshness.as_dict() if self.freshness else None,
            "rules": [result.as_dict() for result in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """The report as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def write_json(self, path: str | Path) -> Path:
        """Write the report JSON to ``path`` (creating parent directories)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path
