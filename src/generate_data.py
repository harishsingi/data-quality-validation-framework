"""Legacy entry point: ``python -m src.generate_data ...``.

Delegates to :func:`src.dq.cli.main_generate`. Prefer ``dq-generate`` (after
``pip install -e .``) or ``python -m src.dq.cli generate ...``.
"""

from src.dq.cli import main_generate

if __name__ == "__main__":
    raise SystemExit(main_generate())
