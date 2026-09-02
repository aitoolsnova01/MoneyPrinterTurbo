#!/usr/bin/env python3
"""Persistent automation worker for MoneyPrinterTurbo scheduled Shorts."""

from __future__ import annotations

import argparse
import threading

from app.services import automation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="process at most one pending automation action or scheduled run and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.once:
        automation.run_once()
        return 0

    stop_event = threading.Event()
    automation.worker_loop(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
