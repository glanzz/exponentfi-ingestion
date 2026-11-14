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
import re
import tempfile
from typing import Iterable, Sequence

from ..config import OUTPUT_COLUMNS, REJECT_COLUMNS
from ..models import LedgerLine

# Characters that make a spreadsheet treat a cell as a formula when the leading
# char is one of these. The output is meant to be opened by a human bookkeeper,
# and both feed-controlled ids and the rejects echo of raw rows flow into CSVs,
# so neutralize them. See OWASP "CSV Injection".
_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")
# A plain number (our own amounts) may legitimately start with '-' / '+'; those
# are not formulas, so leave them untouched to avoid corrupting the ledger.
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def sanitize_cell(value: str) -> str:
    """Neutralize CSV/formula injection: prefix a single quote to any string
    that would be interpreted as a formula, except plain numeric values."""
    if not value:
        return value
    if value[0] in _FORMULA_LEADS and not _NUMERIC_RE.match(value):
        return "'" + value
    return value


def _atomic_write_csv(path: str, header: Sequence[str], rows: Iterable[dict]) -> int:
    """Write rows to `path` atomically. Returns the row count.

    Every string cell is run through sanitize_cell so feed-controlled text can't
    smuggle a spreadsheet formula into the output."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    count = 0
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(header), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                safe = {
                    k: sanitize_cell(v) if isinstance(v, str) else v
                    for k, v in row.items()
                }
                writer.writerow(safe)
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
