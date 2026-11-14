"""Property-style tests: idempotency, order-independence, and the money
invariants."""

from __future__ import annotations

import csv
import random

from ledger.pipeline import run


def _bytes(path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def test_running_twice_is_byte_identical(tmp_path, transactions_csv):
    out1 = tmp_path / "a.csv"
    out2 = tmp_path / "b.csv"
    rej = tmp_path / "r.csv"
    run(transactions_csv, str(out1), str(rej))
    run(transactions_csv, str(out2), str(rej))
    assert _bytes(out1) == _bytes(out2)


def test_shuffled_input_gives_same_output(tmp_path, transactions_csv):
    # Baseline output from the real file.
    base_out = tmp_path / "base.csv"
    rej = tmp_path / "r.csv"
    run(transactions_csv, str(base_out), str(rej))

    # Build a shuffled copy of the input (header kept on top).
    with open(transactions_csv, newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    header, rows = reader[0], reader[1:]
    rnd = random.Random(1234)
    rnd.shuffle(rows)
    shuffled = tmp_path / "shuffled.csv"
    with open(shuffled, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    shuf_out = tmp_path / "shuf.csv"
    run(str(shuffled), str(shuf_out), str(rej))

    assert _bytes(base_out) == _bytes(shuf_out)


def test_resume_flag_produces_same_output(tmp_path, transactions_csv):
    out = tmp_path / "o.csv"
    rej = tmp_path / "r.csv"
    run(transactions_csv, str(out), str(rej))
    first = _bytes(out)
    # Resume with no checkpoint present must behave like a clean run.
    run(transactions_csv, str(out), str(rej), resume=True)
    assert _bytes(out) == first


def test_amounts_have_exactly_two_decimals(tmp_path, transactions_csv):
    out = tmp_path / "o.csv"
    rej = tmp_path / "r.csv"
    run(transactions_csv, str(out), str(rej))
    with open(out, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            amt = row["amount"]
            assert "." in amt and len(amt.split(".")[1]) == 2
            assert amt != "-0.00"
