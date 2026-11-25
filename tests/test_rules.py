"""Tests for src.dq.rules: individual checks and the compat validate()."""

import unittest

from src.dq.config import RuleConfig
from src.dq.rules import (
    check_allowed_values,
    check_column_types,
    check_not_null,
    check_range,
    check_reference,
    check_schema,
    check_unique,
    validate,
)

ROWS = [
    {"id": "1", "customer_id": "C1", "amount": "100", "updated_at": "2026-11-22T10:00:00Z"},
    {"id": "2", "customer_id": "C2", "amount": "200", "updated_at": "2026-11-22T10:00:00Z"},
]
CONFIG = RuleConfig(
    required_columns=("id", "customer_id", "amount", "updated_at"),
    column_types={"id": "int", "amount": "float", "updated_at": "datetime"},
    not_null=("customer_id",),
    unique=("id",),
    ranges=(),
)
FULL_CONFIG = RuleConfig(
    required_columns=("id", "customer_id", "amount", "updated_at"),
    not_null=("customer_id",),
    unique=("id",),
    ranges=(),
)


class TestSchema(unittest.TestCase):
    def test_clean_rows_pass(self):
        result = check_schema(ROWS, ["id", "customer_id", "amount", "updated_at"])
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.passed, 4)  # passed counts required columns

    def test_missing_column_fails_batch(self):
        result = check_schema(ROWS, ["id", "customer_id", "amount", "nope"])
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.failures[0].record_id, "batch")
        self.assertIn("nope", result.failures[0].detail)

    def test_empty_rows_fail(self):
        result = check_schema([], ["id"])
        self.assertEqual(result.failed, 1)
        self.assertIn("no rows", result.failures[0].detail)


class TestColumnTypes(unittest.TestCase):
    def test_clean_types_pass(self):
        results = check_column_types(ROWS, {"id": "int", "amount": "float"})
        self.assertTrue(all(r.failed == 0 for r in results))

    def test_bad_int_and_bad_datetime_fail(self):
        rows = [
            {"id": "x", "amount": "10", "updated_at": "not-a-date"},
            {"id": "2", "amount": "abc", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        results = {r.rule: r for r in check_column_types(
            rows, {"id": "int", "amount": "float", "updated_at": "datetime"}
        )}
        self.assertEqual(results["schema:type:id"].failed, 1)
        self.assertEqual(results["schema:type:amount"].failed, 1)
        self.assertEqual(results["schema:type:updated_at"].failed, 1)

    def test_empty_value_skipped_not_a_type_failure(self):
        rows = [{"id": "", "amount": "10", "updated_at": "2026-11-22T10:00:00Z"}]
        results = check_column_types(rows, {"id": "int"})
        self.assertEqual(results[0].failed, 0)
        self.assertEqual(results[0].passed, 0)


class TestNotNull(unittest.TestCase):
    def test_blank_and_whitespace_count_as_null(self):
        rows = ROWS + [
            {"id": "3", "customer_id": "", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
            {"id": "4", "customer_id": "   ", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        result = check_not_null(rows, "customer_id")
        self.assertEqual((result.passed, result.failed), (2, 2))


class TestUnique(unittest.TestCase):
    def test_duplicate_fails_second_occurrence_only(self):
        rows = ROWS + [
            {"id": "1", "customer_id": "C9", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        result = check_unique(rows, "id")
        self.assertEqual((result.passed, result.failed), (2, 1))
        self.assertEqual(result.failures[0].record_id, "1")

    def test_empty_values_are_not_duplicates(self):
        rows = [
            {"id": "", "customer_id": "C1", "amount": "1", "updated_at": "2026-11-22T10:00:00Z"},
            {"id": "", "customer_id": "C2", "amount": "1", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        result = check_unique(rows, "id")
        self.assertEqual(result.failed, 0)


class TestRange(unittest.TestCase):
    def test_boundaries_are_inclusive(self):
        rows = [
            {"id": "1", "amount": "0"},
            {"id": "2", "amount": "150"},
            {"id": "3", "amount": "151"},
        ]
        result = check_range(rows, "amount", 0, 150)
        self.assertEqual((result.passed, result.failed), (2, 1))

    def test_non_numeric_fails_and_empty_is_skipped(self):
        rows = [
            {"id": "1", "amount": "abc"},
            {"id": "2", "amount": ""},
        ]
        result = check_range(rows, "amount", 0, 150)
        self.assertEqual((result.passed, result.failed), (0, 1))
        self.assertIn("not numeric", result.failures[0].detail)


class TestAllowedAndReference(unittest.TestCase):
    def test_allowed_values(self):
        result = check_allowed_values(ROWS, "customer_id", frozenset({"C1"}))
        self.assertEqual((result.passed, result.failed), (1, 1))

    def test_reference_check(self):
        result = check_reference(ROWS, "customer_id", frozenset({"C1", "C2"}))
        self.assertEqual(result.failed, 0)
        result = check_reference(ROWS, "customer_id", frozenset({"C1"}))
        self.assertEqual(result.failed, 1)
        self.assertIn("no match", result.failures[0].detail)


class TestValidateCompat(unittest.TestCase):
    def test_clean_rows_pass(self):
        results, quarantined = validate(ROWS, CONFIG)
        self.assertEqual(quarantined, [])
        self.assertTrue(all(r.failed == 0 for r in results))

    def test_null_is_quarantined(self):
        rows = ROWS + [
            {"id": "3", "customer_id": "", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        _, quarantined = validate(rows, FULL_CONFIG)
        self.assertEqual(quarantined, ["3"])

    def test_duplicate_is_quarantined(self):
        rows = ROWS + [
            {"id": "1", "customer_id": "C9", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
        ]
        _, quarantined = validate(rows, FULL_CONFIG)
        self.assertEqual(quarantined, ["1"])


if __name__ == "__main__":
    unittest.main()
