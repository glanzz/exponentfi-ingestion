"""Output writers.

Two kinds of write:
  - the final ledger (and rejects) are written to a temp file and atomically
    os.replace'd into place, so a crash never leaves a half-written ledger and a
    rerun produces byte-identical output (idempotency);
  - the rejects writer is a small streaming helper used during the run.
"""

from __future__ import annotations

import csv
import os
import tempfile
from typing import Iterable, Sequence

from ..config import OUTPUT_COLUMNS, REJECT_COLUMNS
from ..models import LedgerLine


def _atomic_write_csv(path: str, header: Sequence[str], rows: Iterable[dict]) -> int:
    """Write rows to `path` atomically. Returns the row count."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    count = 0
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(header), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
                count += 1
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on POSIX
        return count
    except BaseException:
        # Don't leave a stray temp file behind on failure.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_ledger(path: str, lines: Iterable[LedgerLine]) -> int:
    """Materialize the ledger view: sort (date, id), dedupe by transaction_id
    (last wins — but input is already unique per id), atomic replace.

    The id-keyed dedupe here is the idempotency backstop: even if a row were
    emitted twice (e.g. a sloppy resume), it collapses to one line."""
    by_id: dict[str, LedgerLine] = {}
    for line in lines:
        by_id[line.transaction_id] = line
    ordered = sorted(by_id.values(), key=lambda l: l.sort_key())
    return _atomic_write_csv(
        path, OUTPUT_COLUMNS, (l.as_output_row() for l in ordered)
    )


def write_rejects(path: str, reject_rows: Iterable[dict]) -> int:
    """Always written, even when empty, so a clean run leaves an empty rejects
    file rather than an ambiguous absence."""
    return _atomic_write_csv(path, REJECT_COLUMNS, reject_rows)
