"""Tests for src.dq.freshness."""

import unittest
from datetime import datetime, timezone

from src.dq.freshness import check_freshness, latest_timestamp, parse_timestamp

ROWS = [
    {"id": "1", "updated_at": "2026-11-22T10:00:00Z"},
    {"id": "2", "updated_at": "2026-11-20T10:00:00Z"},
]
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


class TestParseTimestamp(unittest.TestCase):
    def test_zulu_and_date_only(self):
        self.assertEqual(
            parse_timestamp("2026-11-22T10:00:00Z"),
            datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            parse_timestamp("2026-11-22"),
            datetime(2026, 11, 22, 0, 0, tzinfo=timezone.utc),
        )

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_timestamp("not-a-date"))
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp(None))


class TestLatestTimestamp(unittest.TestCase):
    def test_latest_and_invalid_count(self):
        rows = ROWS + [{"id": "3", "updated_at": "garbage"}]
        latest, invalid = latest_timestamp(rows)
        self.assertEqual(latest, datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(invalid, 1)

    def test_no_rows(self):
        latest, invalid = latest_timestamp([])
        self.assertIsNone(latest)
        self.assertEqual(invalid, 0)


class TestCheckFreshness(unittest.TestCase):
    def test_passes_and_fails_on_expected_date(self):
        self.assertTrue(check_freshness(ROWS, expected_date="2026-11-22").passed)
        result = check_freshness(ROWS, expected_date="2026-11-23")
        self.assertFalse(result.passed)
        self.assertIn("before expected", result.detail)

    def test_no_timestamps_fails(self):
        result = check_freshness([{"id": "1"}], expected_date="2026-11-22")
        self.assertFalse(result.passed)
        self.assertIsNone(result.latest)

    def test_max_age(self):
        self.assertTrue(
            check_freshness(ROWS, max_age_hours=48, now=NOW).passed
        )
        self.assertFalse(
            check_freshness(ROWS, max_age_hours=1, now=NOW).passed
        )

    def test_invalid_timestamps_do_not_crash_check(self):
        rows = ROWS + [{"id": "3", "updated_at": "garbage"}]
        result = check_freshness(rows, expected_date="2026-11-22")
        self.assertTrue(result.passed)
        self.assertEqual(result.invalid_timestamps, 1)


if __name__ == "__main__":
    unittest.main()
