"""I/O layer: reader validation, atomic writer, checkpoint fingerprint guard."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

import pytest

from ledger.constants.enums import LineType
from ledger.errors import CheckpointMismatchError, MissingColumnsError
from ledger.io import checkpoint_store, input_fingerprint, stream_rows, write_ledger
from ledger.io.reader import count_data_rows
from ledger.models import Checkpoint
from ledger.models.ledger_line import LedgerLine


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_missing_columns_raises(tmp_path):
    p = _write(tmp_path / "bad.csv", "id,date,amount\ntxn_1,2026-08-03,1.00\n")
    with pytest.raises(MissingColumnsError):
        list(stream_rows(p))


def test_empty_file_raises(tmp_path):
    p = _write(tmp_path / "empty.csv", "")
    with pytest.raises(MissingColumnsError):
        list(stream_rows(p))


def test_blank_lines_skipped(tmp_path):
    p = _write(
        tmp_path / "ok.csv",
        "id,sync_batch,date,account,merchant,memo,amount\n"
        "txn_1,1,2026-08-03,card,SYSCO,SYSCO,1.00\n"
        "\n"
        "txn_2,1,2026-08-03,card,SYSCO,SYSCO,2.00\n",
    )
    rows = list(stream_rows(p))
    assert [r.id for r in rows] == ["txn_1", "txn_2"]


def test_count_data_rows(tmp_path):
    p = _write(
        tmp_path / "c.csv",
        "id,sync_batch,date,account,merchant,memo,amount\n"
        "a,1,2026-08-03,card,x,x,1\n"
        "b,1,2026-08-03,card,x,x,2\n",
    )
    assert count_data_rows(p) == 2


def test_writer_is_atomic_and_deduped(tmp_path):
    out = tmp_path / "led.csv"
    line = LedgerLine(
        transaction_id="txn_1",
        date=date(2026, 8, 3),
        type=LineType.PURCHASE,
        category="Food & beverage",
        amount=Decimal("1.00"),
        needs_review=False,
    )
    # Same id twice -> collapses to one line (idempotency backstop).
    n = write_ledger(str(out), [line, line])
    assert n == 1
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1


def test_checkpoint_roundtrip_and_fingerprint_guard(tmp_path):
    inp = _write(
        tmp_path / "in.csv",
        "id,sync_batch,date,account,merchant,memo,amount\na,1,2026-08-03,card,x,x,1\n",
    )
    fp = input_fingerprint(inp)
    cp_path = str(tmp_path / "cp.json")
    cp = Checkpoint(
        input_fingerprint=fp,
        source_line=10,
        byte_offset=0,
        rows_emitted=5,
        rows_rejected=0,
    )
    checkpoint_store.save(cp_path, cp)

    # Same fingerprint -> loads.
    loaded = checkpoint_store.load_for_input(cp_path, fp)
    assert loaded is not None and loaded.source_line == 10

    # Different fingerprint -> refuses.
    with pytest.raises(CheckpointMismatchError):
        checkpoint_store.load_for_input(cp_path, "deadbeef")


def test_corrupt_checkpoint_is_ignored(tmp_path):
    cp_path = tmp_path / "cp.json"
    cp_path.write_text("{not json", encoding="utf-8")
    assert checkpoint_store.load(str(cp_path)) is None
