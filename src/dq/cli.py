"""Command-line interface.

Two commands, one entry point each (see ``pyproject.toml``)::

    dq-validate --dataset data/records.csv --rules rules/orders.yaml
    dq-generate --output-dir data

Without installing, run from the repository root with
``PYTHONPATH=src python -m src.dq.cli validate ...`` (same for
``generate``). Legacy entry points ``python -m src.run_validation`` and
``python -m src.generate_data`` still work and delegate here.

Exit codes: 0 = validation passed, 1 = validation ran but failed
(rules or freshness), 2 = error (missing file, bad config, bad arguments).
No network or API calls are made anywhere in this framework, so there is
no retry/backoff logic to add; the only external inputs are local files,
and failures there are reported as errors, not retried.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .config import load_config
from .constants import (
    CLEAN_FILENAME,
    DEFAULT_DATASET_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RULES_PATH,
    QUARANTINE_FILENAME,
    REPORT_FILENAME,
)
from .errors import DataQualityError
from .freshness import check_freshness
from .generator import (
    DEFAULT_SEED,
    REFERENCE_DATE,
    CLEAN_ROW_COUNT,
    write_dataset,
)
from .io import load_csv
from .logging_config import setup_logging
from .quarantine import write_clean, write_quarantine
from .validator import validate

logger = logging.getLogger(__name__)


def _validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq-validate",
        description="Validate a CSV dataset against a YAML rule config.",
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET_PATH)
    parser.add_argument("--rules", default=DEFAULT_RULES_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--log-level", default="INFO")
    return parser


def _generate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq-generate",
        description="Generate the synthetic dataset and customer master list.",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--clean-count", type=int, default=CLEAN_ROW_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--reference-date", default=REFERENCE_DATE.isoformat())
    parser.add_argument("--log-level", default="INFO")
    return parser


def run_validate(args: argparse.Namespace) -> int:
    """Validate one dataset. Returns a process exit code (0, 1, or 2)."""
    setup_logging(args.log_level)
    try:
        config = load_config(args.rules)
        dataset = load_csv(args.dataset)
        report = validate(dataset.rows, config)
        freshness = check_freshness(
            dataset.rows,
            expected_date=config.expected_date,
            max_age_hours=config.max_age_hours,
        )
        report.attach_freshness(freshness)
    except DataQualityError as exc:
        logger.error("%s", exc)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = [f for result in report.results for f in result.failures]
    quarantined_rows = 0
    if report.quarantined_ids:
        quarantined_rows = write_quarantine(
            dataset.rows, failures, output_dir / QUARANTINE_FILENAME
        )
        logger.info(
            "quarantined %d records to %s (never to gold)",
            quarantined_rows,
            output_dir / QUARANTINE_FILENAME,
        )
    else:
        logger.info("no records quarantined")
    clean_rows = write_clean(
        dataset.rows,
        report.quarantined_ids,
        output_dir / CLEAN_FILENAME,
        fieldnames=dataset.fieldnames,
    )
    report_path = report.write_json(output_dir / REPORT_FILENAME)
    for result in report.results:
        logger.info(
            "%s: %s (%d passed, %d failed)",
            result.rule,
            "PASS" if result.failed == 0 else "FAIL",
            result.passed,
            result.failed,
        )
    logger.info(
        "freshness: %s (%s)",
        "PASS" if freshness.passed else "FAIL",
        freshness.detail,
    )
    logger.info(
        "rows in=%d rows out=%d rejected=%d report=%s",
        report.rows_in,
        clean_rows,
        report.rejected_rows,
        report_path,
    )
    print(report.to_json())
    return 0 if report.passed else 1


def run_generate(args: argparse.Namespace) -> int:
    """Generate the synthetic dataset. Returns a process exit code (0 or 2)."""
    setup_logging(args.log_level)
    if args.clean_count < 0:
        logger.error("--clean-count must be 0 or more, got %d", args.clean_count)
        return 2
    try:
        reference_date = date.fromisoformat(args.reference_date)
    except ValueError:
        logger.error("--reference-date must be YYYY-MM-DD, got %r", args.reference_date)
        return 2
    paths = write_dataset(
        args.output_dir,
        clean_count=args.clean_count,
        seed=args.seed,
        reference_date=reference_date,
    )
    total = args.clean_count + 3
    logger.info(
        "wrote %d synthetic records (%d clean, 3 bad to exercise quarantine) to %s",
        total,
        args.clean_count,
        paths["records"],
    )
    logger.info("wrote %d synthetic customers to %s", args.clean_count, paths["customers"])
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch ``validate`` / ``generate`` subcommands."""
    parser = argparse.ArgumentParser(
        prog="dq",
        description="Data quality validation framework.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", parents=[_validate_parser()], add_help=False
    )
    validate_parser.set_defaults(func=run_validate)
    generate_parser = subparsers.add_parser(
        "generate", parents=[_generate_parser()], add_help=False
    )
    generate_parser.set_defaults(func=run_generate)
    args = parser.parse_args(argv)
    return args.func(args)


def main_validate(argv: list[str] | None = None) -> int:
    """Console-script entry point for ``dq-validate`` (no subcommand word)."""
    args = _validate_parser().parse_args(argv)
    return run_validate(args)


def main_generate(argv: list[str] | None = None) -> int:
    """Console-script entry point for ``dq-generate`` (no subcommand word)."""
    args = _generate_parser().parse_args(argv)
    return run_generate(args)


if __name__ == "__main__":
    sys.exit(main())
