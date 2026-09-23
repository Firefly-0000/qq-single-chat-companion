from __future__ import annotations

import sys

from .logging_setup import configure_logging
from .ui.main_window import run_gui


def main() -> int:
    configure_logging()
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
