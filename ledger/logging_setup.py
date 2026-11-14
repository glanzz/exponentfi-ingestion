"""Logging and console output.

Rich is used for console polish (level colors, tracebacks, progress, summary
tables). If Rich is somehow unavailable we fall back to stdlib logging rather
than crash — the tool must not fail abruptly over a cosmetic dependency.

Rich is console-only. It never writes to the CSV outputs, so output stays
deterministic and testable.
"""

from __future__ import annotations

import logging
from typing import Iterable

try:  # pragma: no cover - exercised implicitly
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.table import Table

    _RICH = True
except Exception:  # pragma: no cover
    _RICH = False

_console = Console(stderr=True) if _RICH else None


def get_console():
    return _console


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ledger")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False
    if _RICH:
        handler = RichHandler(
            console=_console, rich_tracebacks=True, show_path=False, markup=False
        )
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
    logger.addHandler(handler)
    return logger


def print_summary(
    *,
    rows_read: int,
    rows_emitted: int,
    rows_rejected: int,
    type_counts: dict[str, int],
    review_count: int,
    reject_reasons: dict[str, int],
    elapsed_s: float,
    output_path: str,
    rejects_path: str,
) -> None:
    """End-of-run summary. Rich table if available, plain text otherwise."""
    if _RICH and _console is not None:
        t = Table(title="Ledger run summary", show_lines=False)
        t.add_column("Metric", style="bold")
        t.add_column("Value", justify="right")
        t.add_row("Rows read", str(rows_read))
        t.add_row("Ledger lines written", str(rows_emitted))
        t.add_row("Rows rejected", str(rows_rejected))
        t.add_row("Needs review", str(review_count))
        for ltype, n in sorted(type_counts.items()):
            t.add_row(f"  type: {ltype}", str(n))
        for reason, n in sorted(reject_reasons.items()):
            t.add_row(f"  reject: {reason}", str(n))
        t.add_row("Elapsed", f"{elapsed_s:.2f}s")
        t.add_row("Output", output_path)
        t.add_row("Rejects", rejects_path)
        _console.print(t)
    else:
        lines = [
            "--- Ledger run summary ---",
            f"rows_read={rows_read}",
            f"ledger_lines={rows_emitted}",
            f"rejected={rows_rejected}",
            f"needs_review={review_count}",
            *[f"type.{k}={v}" for k, v in sorted(type_counts.items())],
            *[f"reject.{k}={v}" for k, v in sorted(reject_reasons.items())],
            f"elapsed_s={elapsed_s:.2f}",
            f"output={output_path}",
            f"rejects={rejects_path}",
        ]
        print("\n".join(lines))


def progress_context(total: int | None):
    """A Rich progress bar if available, else a no-op context manager whose
    update() does nothing."""
    if _RICH and _console is not None:
        from rich.progress import (
            BarColumn,
            Progress,
            TextColumn,
            TimeElapsedColumn,
        )

        return Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=_console,
            transient=True,
        )

    class _Noop:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def add_task(self, *a, **k):
            return 0

        def update(self, *a, **k):
            pass

    return _Noop()
