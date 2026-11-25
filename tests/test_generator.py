"""Tests for src.dq.generator: deterministic synthetic data."""

import tempfile
import unittest
from pathlib import Path

from src.dq.generator import (
    generate_customers,
    generate_records,
    write_dataset,
)
from src.dq.io import load_csv


class TestGenerator(unittest.TestCase):
    def test_deterministic_for_same_seed(self):
        self.assertEqual(generate_records(seed=42), generate_records(seed=42))

    def test_different_seed_gives_different_amounts(self):
        amounts_a = [r["amount"] for r in generate_records(seed=42)]
        amounts_b = [r["amount"] for r in generate_records(seed=7)]
        self.assertNotEqual(amounts_a, amounts_b)

    def test_counts_and_bad_rows(self):
        rows = generate_records()
        self.assertEqual(len(rows), 103)  # 100 clean + 3 intentional bad rows
        clean, bad = rows[:100], rows[100:]
        self.assertEqual(bad[0]["id"], 101)
        self.assertEqual(bad[0]["customer_id"], "")
        self.assertEqual(bad[1]["amount"], 99999)
        self.assertEqual(bad[1]["id"], 102)
        self.assertEqual(bad[2]["id"], 102)  # duplicate id
        self.assertEqual(bad[2]["amount"], 20)
        self.assertTrue(all(r["customer_id"] for r in clean))

    def test_latest_clean_row_is_the_reference_date(self):
        rows = generate_records()
        latest = max(r["updated_at"] for r in rows[:100])
        self.assertEqual(latest, "2026-11-22T10:00:00Z")
        self.assertTrue(all(r["updated_at"] <= "2026-11-22T10:00:00Z" for r in rows))

    def test_customers_cover_clean_ids_only(self):
        customers = generate_customers()
        self.assertEqual(len(customers), 100)
        self.assertEqual(customers[0]["customer_id"], "C0001")
        self.assertEqual(customers[-1]["customer_id"], "C0100")

    def test_write_dataset_creates_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_dataset(tmp)
            self.assertTrue(paths["records"].exists())
            self.assertTrue(paths["customers"].exists())
            self.assertEqual(len(load_csv(paths["records"]).rows), 103)
            self.assertEqual(len(load_csv(paths["customers"]).rows), 100)
            # Deterministic: a second write is byte-identical.
            first = paths["records"].read_bytes()
            write_dataset(tmp)
            self.assertEqual(paths["records"].read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
