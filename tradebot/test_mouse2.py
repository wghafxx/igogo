"""Backward-compatible entrypoint for safe mouse diagnostics."""
from test_mouse import main


if __name__ == "__main__":
    raise SystemExit(main())