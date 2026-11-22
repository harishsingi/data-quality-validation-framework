"""Freshness check: read the latest timestamp, alert if no new data."""
from datetime import datetime

def latest_timestamp(rows, column="updated_at"):
    stamps = [r[column] for r in rows if r.get(column)]
    return max(stamps) if stamps else None

def check_freshness(rows, column="updated_at", expected_date=None):
    """Pass when the latest timestamp is on/after expected_date (YYYY-MM-DD)."""
    latest = latest_timestamp(rows, column)
    if latest is None:
        return False, "no timestamps found"
    if expected_date and latest[:10] < expected_date:
        return False, f"latest {latest} is before expected {expected_date}"
    return True, f"latest {latest}"
