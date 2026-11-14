"""End-to-end integrity: generate random feeds, run the real pipeline to CSV,
read it back, and prove date and amount are never corrupted and dedupe/classify
hold for every surviving row.

This is the strongest reliability check: it exercises parse -> dedupe -> classify
-> atomic write -> re-read, the exact path production uses.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from strategies import (
    JUNK_MERCHANTS,
    KNOWN_MERCHANTS,
    NON_TRANSFER_MEMOS,
    TRANSFER_MEMOS,
    TRANSFER_MERCHANTS,
    expected_classification,
)

from ledger.constants.enums import Account
from ledger.models import Transaction
from ledger.models.ledger_line import _format_amount
from ledger.pipeline import run

# A feed row as the generator produces it: valid, well-formed values so every row
# is expected to survive to the ledger (no rejects), which lets us check a 1:1
# mapping from input id -> output row.
_merchant = st.one_of(
    st.sampled_from(KNOWN_MERCHANTS),
    st.sampled_from(JUNK_MERCHANTS[:-1]),  # drop the "" entry; keep merchant non-empty
    st.sampled_from(TRANSFER_MERCHANTS),
)
_memo = st.one_of(st.sampled_from(TRANSFER_MEMOS), st.sampled_from(NON_TRANSFER_MEMOS))
_amount = st.decimals(
    min_value=Decimal("-99999.99"),
    max_value=Decimal("99999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)
_date = st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31))


@st.composite
def feed_rows(draw):
    """A list of raw feed dicts that reuses ids across DIFFERENT batches to
    exercise cross-batch dedupe, while never colliding on the same (id, batch)
    pair — so every row is a clean pending/posted re-sync, not a feed-bug
    duplicate. (Same-batch duplicates are covered directly in the dedupe tests;
    here we want a clean 1:1 id->output mapping to check date/amount integrity.)"""
    n = draw(st.integers(min_value=1, max_value=25))
    rows = []
    used_batches: dict[str, set[int]] = {}
    for i in range(n):
        reuse = draw(st.booleans()) and rows
        rid = draw(st.sampled_from(sorted(used_batches))) if reuse and used_batches else f"txn_{i}"
        taken = used_batches.setdefault(rid, set())
        # Pick a batch not yet used for this id.
        candidates = [b for b in range(1, 10) if b not in taken]
        if not candidates:
            rid = f"txn_{i}"  # id exhausted its batch space; fall back to fresh
            taken = used_batches.setdefault(rid, set())
            candidates = list(range(1, 10))
        batch = draw(st.sampled_from(candidates))
        taken.add(batch)
        rows.append(
            {
                "id": rid,
                "sync_batch": str(batch),
                "date": draw(_date).isoformat(),
                "account": draw(st.sampled_from(["card", "bank"])),
                "merchant": draw(_merchant),
                "memo": draw(_memo),
                "amount": _format_amount(draw(_amount)),
            }
        )
    return rows


def _write_feed(path, rows):
    cols = ["id", "sync_batch", "date", "account", "merchant", "memo", "amount"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


@given(feed_rows())
@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_pipeline_preserves_date_amount_and_dedupe(tmp_path_factory, rows):
    tmp = tmp_path_factory.mktemp("feed")
    inp = tmp / "in.csv"
    out = tmp / "out.csv"
    rej = tmp / "rej.csv"
    _write_feed(inp, rows)

    stats = run(str(inp), str(out), str(rej))

    # All generated rows are well-formed -> nothing rejected.
    assert stats.rows_rejected == 0

    # Independent dedupe oracle: winning raw row per id = max batch (ties -> last
    # occurrence in file order, matching the implementation).
    winner_raw = {}
    for r in rows:
        b = int(r["sync_batch"])
        prev = winner_raw.get(r["id"])
        if prev is None or b >= int(prev["sync_batch"]):
            winner_raw[r["id"]] = r

    with open(out, newline="", encoding="utf-8") as f:
        produced = {row["transaction_id"]: row for row in csv.DictReader(f)}

    # One output line per unique id.
    assert set(produced) == set(winner_raw)

    for tid, win in winner_raw.items():
        got = produced[tid]
        # DATE never corrupted.
        assert got["date"] == win["date"], f"date corrupted for {tid}"
        # AMOUNT never corrupted (value + sign), 2 decimals.
        assert got["amount"] == win["amount"], f"amount corrupted for {tid}"
        # TYPE/CATEGORY match the independent oracle on the winning row.
        txn = Transaction(
            id=tid,
            sync_batch=int(win["sync_batch"]),
            date=date.fromisoformat(win["date"]),
            account=Account(win["account"]),
            merchant=win["merchant"],
            memo=win["memo"],
            amount=Decimal(win["amount"]),
        )
        exp_type, exp_cat, exp_review = expected_classification(txn)
        assert got["type"] == exp_type.value, f"type wrong for {tid}"
        assert got["category"] == exp_cat, f"category wrong for {tid}"
        assert got["needs_review"] == ("true" if exp_review else "false")
