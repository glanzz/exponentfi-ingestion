"""CSV/formula-injection defense on output cells.

Feed-controlled fields (transaction_id, category/merchant text) end up in CSVs a
human opens in Excel/Sheets. A cell beginning with = + - @ tab or CR can execute
as a formula. We neutralize those, but must NOT corrupt our own numeric amounts,
which legitimately start with '-'.
"""

from __future__ import annotations

from ledger.io.writer import sanitize_cell


def test_formula_triggers_are_prefixed():
    for payload in ("=1+1", "+1+1", "@SUM(A1)", "=cmd|'/c calc'!A1"):
        out = sanitize_cell(payload)
        assert out.startswith("'"), f"{payload!r} not neutralized -> {out!r}"


def test_control_char_leads_are_prefixed():
    assert sanitize_cell("\tfoo").startswith("'")
    assert sanitize_cell("\rfoo").startswith("'")


def test_plain_negative_number_is_untouched():
    # Our amounts must survive verbatim or the golden test breaks.
    for amt in ("-2210.45", "-0.01", "-5000.00"):
        assert sanitize_cell(amt) == amt


def test_plain_positive_and_text_untouched():
    assert sanitize_cell("1842.17") == "1842.17"
    assert sanitize_cell("txn_1001") == "txn_1001"
    assert sanitize_cell("Food & beverage") == "Food & beverage"
    assert sanitize_cell("") == ""


def test_dash_text_that_is_not_a_number_is_prefixed():
    # A merchant/id like "-SYSCO" is not a number, so it gets neutralized.
    assert sanitize_cell("-SYSCO EVIL").startswith("'")


def test_end_to_end_malicious_merchant_is_escaped(tmp_path):
    import csv
    from datetime import date
    from decimal import Decimal

    from ledger.constants.enums import LineType
    from ledger.io.writer import write_ledger
    from ledger.models import LedgerLine

    evil = LedgerLine(
        transaction_id="=HYPERLINK(1)",
        date=date(2026, 8, 3),
        type=LineType.PURCHASE,
        category="Food & beverage",
        amount=Decimal("-10.00"),
        needs_review=False,
    )
    out = tmp_path / "led.csv"
    write_ledger(str(out), [evil])
    with open(out, newline="", encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f))
    assert row["transaction_id"].startswith("'")
    assert row["amount"] == "-10.00"  # number preserved
