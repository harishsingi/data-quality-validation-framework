"""Tests for src.dq.config: config loading and validation."""

import tempfile
import unittest
from pathlib import Path

from src.dq.config import load_config
from src.dq.errors import ConfigError

MINIMAL = """required_columns: [id, customer_id, amount, updated_at]
"""


class TestLoadConfig(unittest.TestCase):
    def _write(self, directory, text, name="rules.yaml"):
        path = Path(directory) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_minimal_config_loads_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(self._write(tmp, MINIMAL))
        self.assertEqual(config.required_columns, ("id", "customer_id", "amount", "updated_at"))
        self.assertEqual(config.not_null, ())
        self.assertEqual(config.unique, ())
        self.assertEqual(config.ranges, ())
        self.assertIsNone(config.expected_date)
        self.assertIsNone(config.max_age_hours)

    def test_full_config_parses(self):
        text = MINIMAL + """column_types: {id: int, amount: float}
not_null: [customer_id]
unique: [id]
range: {amount: [0, 10000]}
allowed_values: {customer_id: [C0001, C0002]}
reference: {customer_id: {values: [C0001]}}
expected_date: "2026-11-22"
max_age_hours: 48
"""
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(self._write(tmp, text))
        self.assertEqual(config.column_types, {"id": "int", "amount": "float"})
        self.assertEqual(config.ranges[0].column, "amount")
        self.assertEqual((config.ranges[0].low, config.ranges[0].high), (0.0, 10000.0))
        self.assertEqual(config.allowed_values["customer_id"], frozenset({"C0001", "C0002"}))
        self.assertEqual(config.references[0].values, frozenset({"C0001"}))
        self.assertEqual(str(config.expected_date), "2026-11-22")
        self.assertEqual(config.max_age_hours, 48.0)

    def test_missing_file_raises_config_error(self):
        with self.assertRaises(ConfigError):
            load_config("does/not/exist.yaml")

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, ""))

    def test_unknown_key_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "surprise_key: 1\n"))

    def test_missing_required_columns_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, "not_null: [id]\n"))

    def test_range_low_above_high_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "range: {amount: [100, 0]}\n"))

    def test_range_wrong_length_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "range: {amount: [0]}\n"))

    def test_bad_expected_date_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + 'expected_date: "22-11-2026"\n'))

    def test_rule_on_unknown_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "not_null: [nope]\n"))

    def test_unknown_column_type_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "column_types: {id: boolean}\n"))

    def test_negative_max_age_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "max_age_hours: -5\n"))

    def test_reference_needs_values_or_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(self._write(tmp, MINIMAL + "reference: {customer_id: {}}\n"))

    def test_reference_file_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(
                    self._write(
                        tmp,
                        MINIMAL + "reference: {customer_id: {file: nope.csv}}\n",
                    )
                )

    def test_reference_file_resolves_next_to_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "customers.csv").write_text(
                "customer_id\nC0001\nC0002\n", encoding="utf-8"
            )
            config = load_config(
                self._write(
                    tmp,
                    MINIMAL + "reference: {customer_id: {file: customers.csv}}\n",
                )
            )
            self.assertEqual(config.references[0].column, "customer_id")
            self.assertTrue(config.references[0].file is not None)
            self.assertTrue(config.references[0].file.exists())


if __name__ == "__main__":
    unittest.main()
