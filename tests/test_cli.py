"""Tests for src.dq.cli: end-to-end generate + validate, exit codes."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.dq.cli import main, main_generate, main_validate

RULES = """required_columns: [id, customer_id, amount, updated_at]
column_types: {id: int, amount: float, updated_at: datetime}
not_null: [customer_id, amount]
unique: [id]
range: {amount: [0, 10000]}
reference:
  customer_id:
    file: customers.csv
    column: customer_id
expected_date: "2026-11-22"
"""


class TestCli(unittest.TestCase):
    def _setup_generated(self, tmp):
        """Generate data in tmp; write the rules file there; return paths."""
        tmp = Path(tmp)
        self.assertEqual(
            main_generate(
                ["--output-dir", str(tmp), "--log-level", "CRITICAL"]
            ),
            0,
        )
        rules = tmp / "rules.yaml"
        rules.write_text(RULES, encoding="utf-8")
        return tmp / "records.csv", rules

    def _run_validate(self, dataset, rules, out_dir):
        with contextlib.redirect_stdout(io.StringIO()):
            return main_validate(
                [
                    "--dataset",
                    str(dataset),
                    "--rules",
                    str(rules),
                    "--output-dir",
                    str(out_dir),
                    "--log-level",
                    "CRITICAL",
                ]
            )

    def test_generate_then_validate_exits_1_with_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dataset, rules = self._setup_generated(tmp)
            out_dir = tmp / "out"
            self.assertEqual(self._run_validate(dataset, rules, out_dir), 1)
            report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["rows_in"], 103)
            self.assertEqual(report["rows_out"], 100)
            self.assertEqual(report["quarantined_rows"], 3)
            self.assertEqual(report["quarantined_ids"], ["101", "102"])
            self.assertFalse(report["passed"])
            self.assertTrue(report["freshness"]["passed"])
            # Quarantine holds the 3 bad rows; clean holds the 100 good ones.
            from src.dq.io import load_csv

            self.assertEqual(len(load_csv(out_dir / "quarantine.csv").rows), 3)
            self.assertEqual(len(load_csv(out_dir / "clean.csv").rows), 100)

    def test_clean_dataset_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dataset, rules = self._setup_generated(tmp)
            from src.dq.io import load_csv, write_csv

            clean_rows = load_csv(dataset).rows[:100]
            clean_path = tmp / "clean_only.csv"
            write_csv(
                clean_rows,
                clean_path,
                ["id", "customer_id", "amount", "updated_at"],
            )
            self.assertEqual(
                self._run_validate(clean_path, rules, tmp / "out"), 0
            )

    def test_missing_dataset_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _, rules = self._setup_generated(tmp)
            self.assertEqual(
                self._run_validate(tmp / "nope.csv", rules, tmp / "out"), 2
            )

    def test_bad_config_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dataset, _ = self._setup_generated(tmp)
            bad = tmp / "bad.yaml"
            bad.write_text("required_columns: [id]\nrange: {amount: [5, 1]}\n", encoding="utf-8")
            self.assertEqual(
                self._run_validate(dataset, bad, tmp / "out"), 2
            )

    def test_generate_rejects_negative_count_and_bad_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                main_generate(
                    ["--output-dir", tmp, "--clean-count", "-1", "--log-level", "CRITICAL"]
                ),
                2,
            )
            self.assertEqual(
                main_generate(
                    ["--output-dir", tmp, "--reference-date", "22-11-2026",
                     "--log-level", "CRITICAL"]
                ),
                2,
            )

    def test_subcommand_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["generate", "--output-dir", str(tmp), "--log-level", "CRITICAL"]),
                    0,
                )
            self.assertTrue((tmp / "records.csv").exists())


if __name__ == "__main__":
    unittest.main()
