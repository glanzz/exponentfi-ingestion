"""Command-line entry point.

    python -m ledger transactions.csv -o ledger_lines.csv

Exit codes:
    0  clean run, nothing rejected
    1  run completed but some rows were rejected (loud, not silent)
    2  fatal error: bad arguments, missing file, missing columns
"""

from __future__ import annotations

import argparse
import logging
import sys

from .errors import LedgerError
from .logging_setup import print_summary, setup_logging
from .pipeline import run

EXIT_OK = 0
EXIT_REJECTS = 1
EXIT_FATAL = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ledger",
        description="Turn a raw transaction feed into categorized ledger lines.",
    )
    p.add_argument("input", help="path to transactions.csv")
    p.add_argument(
        "-o",
        "--output",
        default="ledger_lines.csv",
        help="output ledger path (default: ledger_lines.csv)",
    )
    p.add_argument(
        "--rejects",
        default=None,
        help="rejected-rows path (default: <output_dir>/rejected_rows.csv)",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="resume a prior interrupted run against the same input",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="debug-level logging"
    )
    return p


def _default_rejects(output: str) -> str:
    import os

    directory = os.path.dirname(os.path.abspath(output)) or "."
    return os.path.join(directory, "rejected_rows.csv")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    log = logging.getLogger("ledger")

    rejects_path = args.rejects or _default_rejects(args.output)

    try:
        stats = run(
            args.input,
            args.output,
            rejects_path,
            resume=args.resume,
        )
    except FileNotFoundError:
        log.error("input file not found: %s", args.input)
        return EXIT_FATAL
    except LedgerError as e:
        # Fatal, whole-run error (e.g. missing required columns).
        log.error(e.render())
        return EXIT_FATAL
    except Exception:  # pragma: no cover - last-resort guard
        log.exception("unexpected fatal error")
        return EXIT_FATAL

    print_summary(
        rows_read=stats.rows_read,
        rows_emitted=stats.rows_emitted,
        rows_rejected=stats.rows_rejected,
        type_counts=stats.type_counts,
        review_count=stats.review_count,
        reject_reasons=stats.reject_reasons,
        elapsed_s=stats.elapsed_s,
        output_path=args.output,
        rejects_path=rejects_path,
    )

    if stats.rows_rejected:
        log.warning(
            "%d row(s) rejected; see %s", stats.rows_rejected, rejects_path
        )
        return EXIT_REJECTS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
