"""Legacy entry point: ``python -m src.run_validation ...``.

Delegates to :func:`src.dq.cli.main_validate`. Prefer ``dq-validate`` (after
``pip install -e .``) or ``python -m src.dq.cli validate ...``.
"""

from src.dq.cli import main_validate

if __name__ == "__main__":
    raise SystemExit(main_validate())
