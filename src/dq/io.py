"""CSV input/output helpers.

Every file read and write in the framework goes through here, so missing
files, empty files, duplicate headers, and ragged rows are reported as
:class:`~src.dq.errors.InputError` with the file and row named, instead of
surfacing as a bare ``csv`` or ``OSError`` traceback. Files are always
opened with a context manager (the original CLI leaked file handles).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .errors import InputError


@dataclass
class CsvDataset:
    """Rows read from a CSV file, plus the header that was seen."""

    rows: list[dict[str, str]] = field(default_factory=list)
    fieldnames: list[str] = field(default_factory=list)


def load_csv(path: str | Path) -> CsvDataset:
    """Read a CSV file into a list of string-valued row dicts.

    Raises:
        InputError: file missing/unreadable, empty, headerless, a header
            column repeated, or a row with more fields than the header.
    """
    path = Path(path)
    try:
        handle = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read dataset {path}: {exc.strerror or exc}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputError(f"dataset {path} is empty (no header row)")
        fieldnames = [name.strip() for name in reader.fieldnames]
        if len(set(fieldnames)) != len(fieldnames):
            raise InputError(f"dataset {path} has duplicate header columns: {fieldnames}")
        rows: list[dict[str, str]] = []
        for line_no, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise InputError(
                    f"dataset {path} line {line_no} has more fields than the header"
                )
            # csv gives None for a missing trailing field; normalise it to ""
            # so every check sees the same "null" representation.
            rows.append({name: (raw_row.get(name) or "") for name in fieldnames})
    return CsvDataset(rows=rows, fieldnames=fieldnames)


def write_csv(rows: list[dict], path: str | Path, fieldnames: list[str]) -> int:
    """Write rows to ``path`` (creating parent directories). Returns rows written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    return len(rows)


def load_reference_values(path: str | Path, column: str) -> frozenset[str]:
    """Load the allowed values of ``column`` from a reference CSV file.

    Empty values are ignored (an empty reference value would match nothing
    meaningful). Raises :class:`InputError` if the file or column is missing.
    """
    dataset = load_csv(path)
    if column not in dataset.fieldnames:
        raise InputError(f"reference file {path} has no column {column!r}")
    return frozenset(
        row[column].strip() for row in dataset.rows if row[column].strip()
    )
