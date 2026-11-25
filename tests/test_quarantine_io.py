"""Tests for src.dq.quarantine and src.dq.io."""

import tempfile
import unittest
from pathlib import Path

from src.dq.errors import InputError
from src.dq.io import load_csv, load_reference_values, write_csv
from src.dq.quarantine import write_clean, write_quarantine
from src.dq.rules import Failure

ROWS = [
    {"id": "1", "customer_id": "C1", "amount": "100", "updated_at": "2026-11-22T10:00:00Z"},
    {"id": "2", "customer_id": "C2", "amount": "200", "updated_at": "2026-11-22T10:00:00Z"},
    {"id": "3", "customer_id": "", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"},
]
FAILURES = [
    Failure("3", "not_null:customer_id", "customer_id is null"),
    Failure("3", "reference:customer_id", "customer_id='' has no match in the reference data"),
]


class TestQuarantine(unittest.TestCase):
    def test_multi_failure_record_appears_once_with_all_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quarantine.csv"
            self.assertEqual(write_quarantine(ROWS, FAILURES, out), 1)
            dataset = load_csv(out)
        self.assertEqual(len(dataset.rows), 1)
        self.assertEqual(dataset.rows[0]["id"], "3")
        self.assertIn("not_null:customer_id", dataset.rows[0]["quarantine_reason"])
        self.assertIn("reference:customer_id", dataset.rows[0]["quarantine_reason"])

    def test_no_failures_writes_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quarantine.csv"
            self.assertEqual(write_quarantine(ROWS, [], out), 0)
            self.assertEqual(load_csv(out).rows, [])

    def test_empty_rows_writes_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quarantine.csv"
            self.assertEqual(write_quarantine([], FAILURES, out), 0)

    def test_repeated_run_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quarantine.csv"
            write_quarantine(ROWS, FAILURES, out)
            first = out.read_bytes()
            write_quarantine(ROWS, FAILURES, out)
            self.assertEqual(out.read_bytes(), first)

    def test_duplicate_id_quarantines_every_row_with_it(self):
        rows = ROWS + [dict(ROWS[1], customer_id="C9")]
        failures = [Failure("2", "unique:id", "duplicate id=2")]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quarantine.csv"
            self.assertEqual(write_quarantine(rows, failures, out), 2)

    def test_duplicate_id_rows_get_only_their_own_reasons(self):
        rows = [
            {"id": "102", "customer_id": "C0102", "amount": "99999",
             "updated_at": "2026-11-22T10:00:00Z"},
            {"id": "102", "customer_id": "C0102", "amount": "20",
             "updated_at": "2026-11-22T10:00:00Z"},
        ]
        failures = [
            Failure("102", "range:amount[0,10000]", "amount=99999 out of range", row_index=0),
            Failure("102", "reference:customer_id", "no match", row_index=0),
            Failure("102", "unique:id", "duplicate id=102", row_index=1),
            Failure("102", "reference:customer_id", "no match", row_index=1),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quarantine.csv"
            self.assertEqual(write_quarantine(rows, failures, out), 2)
            quarantined = load_csv(out).rows
        self.assertIn("range:amount", quarantined[0]["quarantine_reason"])
        self.assertNotIn("unique:id", quarantined[0]["quarantine_reason"])
        self.assertIn("unique:id", quarantined[1]["quarantine_reason"])
        self.assertNotIn("range:amount", quarantined[1]["quarantine_reason"])


class TestWriteClean(unittest.TestCase):
    def test_clean_rows_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "clean.csv"
            self.assertEqual(write_clean(ROWS, ["3"], out), 2)
            self.assertEqual(
                [r["id"] for r in load_csv(out).rows], ["1", "2"]
            )

    def test_empty_rows_needs_fieldnames(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InputError):
                write_clean([], [], Path(tmp) / "clean.csv")
            out = Path(tmp) / "clean.csv"
            self.assertEqual(write_clean([], [], out, fieldnames=["id"]), 0)
            self.assertEqual(load_csv(out).fieldnames, ["id"])


class TestIo(unittest.TestCase):
    def test_missing_file_raises_input_error(self):
        with self.assertRaises(InputError):
            load_csv("does/not/exist.csv")

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(InputError):
                load_csv(path)

    def test_duplicate_header_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.csv"
            path.write_text("id,id\n1,2\n", encoding="utf-8")
            with self.assertRaises(InputError):
                load_csv(path)

    def test_ragged_row_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ragged.csv"
            path.write_text("id,amount\n1,10,extra\n", encoding="utf-8")
            with self.assertRaises(InputError):
                load_csv(path)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv(ROWS, path, ["id", "customer_id", "amount", "updated_at"])
            dataset = load_csv(path)
        self.assertEqual(dataset.rows, ROWS)
        self.assertEqual(
            dataset.fieldnames, ["id", "customer_id", "amount", "updated_at"]
        )

    def test_load_reference_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "customers.csv"
            path.write_text("customer_id\nC1\nC2\n\n", encoding="utf-8")
            self.assertEqual(load_reference_values(path, "customer_id"), {"C1", "C2"})
            with self.assertRaises(InputError):
                load_reference_values(path, "nope")


if __name__ == "__main__":
    unittest.main()
