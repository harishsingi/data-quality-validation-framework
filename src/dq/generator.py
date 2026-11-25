"""Synthetic data generator. No real data.

Generates a small orders-like dataset plus the customer master list the
referential check validates against. Everything is deterministic: a local
``random.Random(seed)`` instance (never the global random state) and dates
derived from a fixed reference date, so the same seed always produces the
same files. The newest clean row lands exactly on the reference date, so
the example config's ``expected_date`` freshness check passes.

Three bad rows are included on purpose, to exercise quarantine:

- id 101: blank ``customer_id`` (not-null failure).
- id 102, amount 99999: out of the configured range, and customer C0102
  is not in the customer master list (range + reference failures).
- id 102 again, amount 20: a duplicate ``id`` (unique failure), also
  with the unknown customer C0102.

That is 3 bad rows but only 2 distinct quarantined ids (101, 102).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from .constants import CUSTOMERS_FILENAME
from .io import write_csv

# Fixed synthetic reference date: the "today" of the synthetic world.
# It is a constant, not a claim about any real system.
REFERENCE_DATE = date(2026, 11, 22)
CLEAN_ROW_COUNT = 100
AMOUNT_MIN = 10
AMOUNT_MAX = 900
DEFAULT_SEED = 42

RECORD_FIELDNAMES = ["id", "customer_id", "amount", "updated_at"]
CUSTOMER_FIELDNAMES = ["customer_id"]


def customer_id_for(index: int) -> str:
    """Synthetic customer id, e.g. index 1 -> ``C0001``."""
    return f"C{index:04d}"


def generate_records(
    clean_count: int = CLEAN_ROW_COUNT,
    seed: int = DEFAULT_SEED,
    reference_date: date = REFERENCE_DATE,
) -> list[dict]:
    """Return ``clean_count`` clean rows plus the 3 intentional bad rows."""
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(1, clean_count + 1):
        # Spread over the 7 days ending on the reference date; the newest
        # clean row is exactly the reference date.
        updated = reference_date - timedelta(days=i % 7)
        rows.append(
            {
                "id": i,
                "customer_id": customer_id_for(i),
                "amount": rng.randint(AMOUNT_MIN, AMOUNT_MAX),
                "updated_at": f"{updated.isoformat()}T10:00:00Z",
            }
        )
    stamp = f"{reference_date.isoformat()}T10:00:00Z"
    rows.append({"id": clean_count + 1, "customer_id": "", "amount": 50, "updated_at": stamp})
    rows.append(
        {
            "id": clean_count + 2,
            "customer_id": customer_id_for(clean_count + 2),
            "amount": 99999,
            "updated_at": stamp,
        }
    )
    rows.append(
        {
            "id": clean_count + 2,
            "customer_id": customer_id_for(clean_count + 2),
            "amount": 20,
            "updated_at": stamp,
        }
    )
    return rows


def generate_customers(clean_count: int = CLEAN_ROW_COUNT) -> list[dict]:
    """The customer master list: one row per clean customer id."""
    return [{"customer_id": customer_id_for(i)} for i in range(1, clean_count + 1)]


def write_dataset(
    output_dir: str | Path,
    clean_count: int = CLEAN_ROW_COUNT,
    seed: int = DEFAULT_SEED,
    reference_date: date = REFERENCE_DATE,
) -> dict[str, Path]:
    """Write ``records.csv`` and ``customers.csv`` into ``output_dir``.

    Returns the paths written. Overwrites deterministically: the same
    arguments always produce byte-identical files.
    """
    output_dir = Path(output_dir)
    records = generate_records(clean_count, seed, reference_date)
    customers = generate_customers(clean_count)
    records_path = output_dir / "records.csv"
    customers_path = output_dir / CUSTOMERS_FILENAME
    write_csv(records, records_path, RECORD_FIELDNAMES)
    write_csv(customers, customers_path, CUSTOMER_FIELDNAMES)
    return {"records": records_path, "customers": customers_path}
