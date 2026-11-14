"""CLI behavior and exit codes: clean run, rejected rows, fatal errors."""

from __future__ import annotations

import csv

from ledger.cli import EXIT_FATAL, EXIT_OK, EXIT_REJECTS, main

HEADER = "id,sync_batch,date,account,merchant,memo,amount\n"


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_clean_run_exit_zero(tmp_path, transactions_csv):
    out = tmp_path / "o.csv"
    rej = tmp_path / "r.csv"
    code = main([transactions_csv, "-o", str(out), "--rejects", str(rej)])
    assert code == EXIT_OK


def test_rejected_rows_exit_one(tmp_path):
    inp = _write(
        tmp_path / "in.csv",
        HEADER
        + "txn_ok,1,2026-08-03,card,SYSCO,SYSCO,1.00\n"
        + "txn_bad,1,2026-08-03,card,SYSCO,SYSCO,notanumber\n"
        + "txn_acct,1,2026-08-03,savings,SYSCO,SYSCO,1.00\n",
    )
    out = tmp_path / "o.csv"
    rej = tmp_path / "r.csv"
    code = main([inp, "-o", str(out), "--rejects", str(rej)])
    assert code == EXIT_REJECTS

    with open(rej, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    reasons = {r["reason"] for r in rows}
    assert reasons == {"malformed_amount", "unknown_account"}

    # The good row still made it to the ledger: bad rows don't sink the run.
    with open(out, newline="", encoding="utf-8") as f:
        ids = [r["transaction_id"] for r in csv.DictReader(f)]
    assert ids == ["txn_ok"]


def test_missing_file_exit_fatal(tmp_path):
    code = main([str(tmp_path / "nope.csv"), "-o", str(tmp_path / "o.csv")])
    assert code == EXIT_FATAL


def test_missing_columns_exit_fatal(tmp_path):
    inp = _write(tmp_path / "bad.csv", "id,amount\ntxn_1,1.00\n")
    code = main([inp, "-o", str(tmp_path / "o.csv"), "--rejects", str(tmp_path / "r.csv")])
    assert code == EXIT_FATAL
