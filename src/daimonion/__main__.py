"""Run daimonion as ``python -m daimonion`` (same entry point as the console script)."""

from daimonion.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
