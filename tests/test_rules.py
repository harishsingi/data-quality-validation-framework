from src.dq.rules import validate, check_range
from src.dq.freshness import check_freshness

ROWS = [
    {"id": "1", "customer_id": "C1", "amount": "100", "updated_at": "2026-11-22T10:00:00Z"},
    {"id": "2", "customer_id": "C2", "amount": "200", "updated_at": "2026-11-22T10:00:00Z"},
]
CONFIG = {"required_columns": ["id", "customer_id", "amount", "updated_at"], "not_null": ["customer_id"], "unique": ["id"], "range": {"amount": [0, 10000]}}

def test_clean_rows_pass():
    results, quarantined = validate(ROWS, CONFIG)
    assert quarantined == []
    assert all(r.failed == 0 for r in results)

def test_null_is_quarantined():
    rows = ROWS + [{"id": "3", "customer_id": "", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"}]
    _, quarantined = validate(rows, CONFIG)
    assert quarantined == ["3"]

def test_duplicate_is_quarantined():
    rows = ROWS + [{"id": "1", "customer_id": "C9", "amount": "50", "updated_at": "2026-11-22T10:00:00Z"}]
    _, quarantined = validate(rows, CONFIG)
    assert quarantined == ["1"]

def test_range_check():
    r = check_range(ROWS, "amount", 0, 150)
    assert r.failed == 1 and r.passed == 1

def test_freshness_passes_and_fails():
    ok, _ = check_freshness(ROWS, expected_date="2026-11-22")
    assert ok
    ok, _ = check_freshness(ROWS, expected_date="2026-11-23")
    assert not ok
