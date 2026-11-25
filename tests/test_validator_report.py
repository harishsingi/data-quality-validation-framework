"""Tests for src.dq.validator and src.dq.report (end-to-end validation)."""

import json
import tempfile
import unittest
from pathlib import Path

from src.dq.config import RuleConfig
from src.dq.freshness import check_freshness
from src.dq.validator import validate

CONFIG = RuleConfig(
    required_columns=("id", "customer_id", "amount", "updated_at"),
    column_types={"id": "int", "amount": "float", "updated_at": "datetime"},
    not_null=("customer_id", "amount"),
    unique=("id",),
)

ROWS = [
    {"id": "1", "customer_id": "C1", "amount": "100", "updated_at": "2026-11-22T10:00:00Z"},
    {"id": "2", "customer_id": "C2", "amount": "200", "updated_at": "2026-11-22T10:00:00Z"},
]


class TestValidator(unittest.TestCase):
    def test_clean_rows_produce_passing_report(self):
        report = validate(ROWS, CONFIG)
        self.assertTrue(report.passed)
        self.assertEqual((report.rows_in, report.rows_out, report.quarantined_rows), (2, 2, 0))
        self.assertEqual(report.quarantined_ids, [])

    def test_bad_rows_quarantined_and_counted(self):
        rows = ROWS + [
            {"id": "3", "customer_id": "", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
            {"id": "2", "customer_id": "C9", "amount": "99999", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        from src.dq.config import RangeRule

        config = RuleConfig(
            required_columns=CONFIG.required_columns,
            not_null=("customer_id",),
            unique=("id",),
            ranges=(RangeRule(column="amount", low=0, high=10000),),
        )
        report = validate(rows, config)
        self.assertFalse(report.passed)
        self.assertEqual(report.quarantined_ids, ["2", "3"])
        # Both rows carrying the duplicated id "2" are quarantined, plus id "3".
        self.assertEqual((report.rows_in, report.rows_out, report.quarantined_rows), (4, 1, 3))

    def test_schema_failure_does_not_quarantine_batch_id(self):
        config = RuleConfig(required_columns=("id", "customer_id", "amount", "missing_col"))
        report = validate(ROWS, config)
        self.assertFalse(report.passed)
        self.assertEqual(report.quarantined_ids, [])
        self.assertEqual(report.quarantined_rows, 0)

    def test_reference_values_supplied_directly(self):
        from src.dq.config import ReferenceRule

        config = RuleConfig(
            required_columns=CONFIG.required_columns,
            references=(ReferenceRule(column="customer_id", values=frozenset({"C1"})),),
        )
        report = validate(ROWS, config)
        self.assertEqual(report.quarantined_ids, ["2"])


class TestReport(unittest.TestCase):
    def test_to_dict_and_passed_property(self):
        report = validate(ROWS, CONFIG)
        data = report.to_dict()
        self.assertEqual(data["rows_in"], 2)
        self.assertEqual(data["rows_out"], 2)
        self.assertEqual(data["quarantined_ids"], [])
        self.assertTrue(data["passed"])
        self.assertIsNone(data["freshness"])
        self.assertTrue(all("passed" in rule and "failed" in rule for rule in data["rules"]))

    def test_freshness_can_fail_an_otherwise_clean_report(self):
        report = validate(ROWS, CONFIG)
        self.assertTrue(report.passed)
        report.attach_freshness(check_freshness(ROWS, expected_date="2026-11-23"))
        self.assertFalse(report.passed)
        self.assertIsNotNone(report.to_dict()["freshness"])
        self.assertIn("2026-11-22", report.to_dict()["freshness"]["detail"])

    def test_write_json_round_trip(self):
        report = validate(ROWS, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = report.write_json(Path(tmp) / "report.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["rows_in"], 2)
        self.assertTrue(loaded["passed"])


if __name__ == "__main__":
    unittest.main()
