"""CLI compatibility wrapper for the USC report generator."""

from __future__ import annotations

from .__main__ import main as _run_main


def main() -> int:
    """Entry point used by ``python -m usc_kommentatoren.cli``."""

    return _run_main()


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
