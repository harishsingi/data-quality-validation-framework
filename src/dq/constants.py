"""Shared constants.

Named here so the same value is never re-typed (and silently drifted) in
two modules.
"""

# Default locations, relative to the repository root when run from there.
DEFAULT_DATASET_PATH = "data/records.csv"
DEFAULT_RULES_PATH = "rules/orders.yaml"
DEFAULT_OUTPUT_DIR = "data"

QUARANTINE_FILENAME = "quarantine.csv"
CLEAN_FILENAME = "clean.csv"
REPORT_FILENAME = "report.json"
CUSTOMERS_FILENAME = "customers.csv"

DEFAULT_ID_COLUMN = "id"

# How many individual failures a single rule result keeps in memory. The
# ``failed`` counter is never capped, only the stored detail list, so a
# pathological input cannot grow the report without bound.
MAX_FAILURES_PER_RULE = 100

# Record id used for batch-level failures (for example a schema failure on
# an empty dataset). It is not a row id and never quarantines a row.
BATCH_RECORD_ID = "batch"

# Column types a rule config may declare. "str" always passes for CSV input
# (every CSV value arrives as a string); the others are validated per row.
SUPPORTED_COLUMN_TYPES = ("int", "float", "str", "datetime")
