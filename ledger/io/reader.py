"""Streaming CSV reader. Yields one RawRow at a time; never loads the whole
file. Also computes the input fingerprint used to guard resume."""

from __future__ import annotations

import csv
import hashlib
import os
from typing import Iterator

from ..config import INPUT_COLUMNS
from ..errors import MissingColumnsError
from ..models import RawRow


def input_fingerprint(path: str) -> str:
    """A cheap, stable identity for the input file: size, mtime, and the first
    few KB. Enough to detect "this is a different feed" without hashing a
    multi-GB file."""
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    h.update(str(int(st.st_mtime)).encode())
    with open(path, "rb") as f:
        h.update(f.read(8192))
    return h.hexdigest()


def _validate_header(fieldnames: list[str] | None, path: str) -> None:
    present = set(fieldnames or [])
    missing = [c for c in INPUT_COLUMNS if c not in present]
    if missing:
        raise MissingColumnsError(
            detail=f"{path}: feed is missing required column(s): {', '.join(missing)}"
        )


def stream_rows(path: str) -> Iterator[RawRow]:
    """Yield RawRow for each data row, one at a time. Never loads the whole file.

    Resume re-reads from the top (the dedupe stage needs every id, and the
    id-keyed atomic write makes re-processing idempotent), so there is no
    byte-seek here — which also sidesteps csv.reader disabling f.tell()."""
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise MissingColumnsError(detail=f"{path}: file is empty")
        _validate_header(header, path)
        header = [c.strip() for c in header]

        line_no = 1  # header was line 1
        for fields in reader:
            line_no += 1
            if not fields or all(c.strip() == "" for c in fields):
                continue  # skip blank lines
            # Zip against the known header; short/long rows are tolerated and
            # surfaced later by the parser's missing-field check.
            mapping = dict(zip(header, fields))
            yield RawRow.from_mapping(mapping, source_line=line_no)


def count_data_rows(path: str) -> int:
    """Total data rows, for sizing decisions (parallelism, dedupe strategy).
    One cheap streaming pass; no parsing."""
    with open(path, "r", newline="", encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)
