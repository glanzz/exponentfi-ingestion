"""End-to-end: the first 15 output rows must match expected_first_15.csv
byte-for-byte, and the run must be well-behaved overall."""

from __future__ import annotations

import csv
import os

from ledger.pipeline import run


def _read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_golden_first_15(tmp_path, transactions_csv, expected_first_15_csv):
    out = tmp_path / "ledger_lines.csv"
    rej = tmp_path / "rejected_rows.csv"
    stats = run(transactions_csv, str(out), str(rej))

    got = _read_rows(out)
    expected = _read_rows(expected_first_15_csv)

    # header + first 15 data rows
    assert got[:16] == expected
    assert stats.rows_rejected == 0


def test_output_row_count_equals_unique_ids(tmp_path, transactions_csv):
    out = tmp_path / "ledger_lines.csv"
    rej = tmp_path / "rejected_rows.csv"
    run(transactions_csv, str(out), str(rej))

    rows = _read_rows(out)[1:]  # drop header
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids))  # no duplicate output ids

    # unique ids in the input (the 60-row feed has 56 unique)
    with open(transactions_csv, newline="", encoding="utf-8") as f:
        src_ids = {r["id"] for r in csv.DictReader(f)}
    assert len(ids) == len(src_ids)


def test_rejects_file_always_written(tmp_path, transactions_csv):
    out = tmp_path / "ledger_lines.csv"
    rej = tmp_path / "rejected_rows.csv"
    run(transactions_csv, str(out), str(rej))
    assert os.path.exists(rej)  # exists even on a clean run
    rows = _read_rows(rej)
    assert rows[0][-2:] == ["reason", "detail"]  # header present
    assert len(rows) == 1  # header only, no rejects
