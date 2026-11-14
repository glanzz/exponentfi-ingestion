"""Hypothesis strategies and an INDEPENDENT spec oracle.

The oracle (`expected_classification`) is written as a flat decision table
straight from the task rules, deliberately structured differently from
`ledger.stages.classify` so the two can't share a bug. If the implementation and
this table ever disagree, one of them is wrong — that's the whole point.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from hypothesis import strategies as st

from ledger.constants.enums import Account, LineType
from ledger.constants.merchants import MERCHANT_CATEGORIES, PAYOUT_MERCHANTS, UNCATEGORIZED
from ledger.models import Transaction

# Known merchant names (as they appear on the list) and some junk that must NOT
# match any of them.
KNOWN_MERCHANTS = sorted(MERCHANT_CATEGORIES)
JUNK_MERCHANTS = [
    "AMZN MKTP US*2K4X9",
    "STAPLES 01188",
    "SHELL OIL 57318",
    "SYSCOLOR PAINT",  # near-miss: must not match SYSCO
    "US FOODSERVICE X",  # near-miss: must not match US FOODS
    "MYSTERY VENDOR",
    "",
]

# Memo fragments that do / do not carry a transfer signal.
TRANSFER_MEMOS = [
    "ONLINE PAYMENT TO CARD 4421",
    "ONLINE PAYMENT - THANK YOU",
    "ONLINE TRANSFER TO SAVINGS 8810",
    "ONLINE TRANSFER FROM SAVINGS 8810",
    "ACH PAYMENT MAINLINE PROPERTIES",
    "payment received",  # lower-case, still a signal
]
NON_TRANSFER_MEMOS = [
    "SYSCO PHILA 8827",
    "GUSTO PAYROLL",  # contains PAYROLL, NOT the whole word PAYMENT
    "INDEED SPONSORED JOB",
    "DAILY PAYOUT",
    "REPAYMENT PLAN",  # contains 'payment' as a substring, not a whole word
    "",
]

# Transfer-counterparty merchant strings (signal lives in the merchant, too).
TRANSFER_MERCHANTS = [
    "ONLINE PAYMENT TO CARD 4421",
    "PAYMENT RECEIVED",
    "TRANSFER TO SAVINGS 8810",
    "TRANSFER FROM SAVINGS 8810",
]


# -- independent oracle, mirroring constants/accounts.py but re-derived ------

_MEMO_SIGNAL = re.compile(r"\b(TRANSFER|PAYMENT)\b", re.IGNORECASE)
_MERCHANT_SIGNAL = re.compile(
    r"(TRANSFER\s+(TO|FROM)\s+SAVINGS|PAYMENT\s+TO\s+CARD|PAYMENT\s+RECEIVED)",
    re.IGNORECASE,
)


def oracle_category(merchant: str) -> tuple[str, bool]:
    """Independent merchant->(category, needs_review). Whole-word prefix, longest
    match wins."""
    norm = re.sub(r"\s+", " ", merchant.strip()).upper()
    best = None
    for name in MERCHANT_CATEGORIES:
        if norm == name or (norm.startswith(name) and not norm[len(name) :][:1].isalnum()):
            if best is None or len(name) > len(best):
                best = name
    if best is None:
        return UNCATEGORIZED, True
    return MERCHANT_CATEGORIES[best], False


def expected_classification(txn: Transaction) -> tuple[LineType, str, bool]:
    """The spec as a flat table. Returns (type, category, needs_review)."""
    category, unknown_review = oracle_category(txn.merchant)
    on_list = category != UNCATEGORIZED
    has_signal = bool(_MEMO_SIGNAL.search(txn.memo) or _MERCHANT_SIGNAL.search(txn.merchant))

    # 1. transfer / conflict
    if has_signal:
        if on_list:
            return (LineType.PURCHASE, UNCATEGORIZED, True)  # conflict -> review
        return (LineType.TRANSFER, "Transfer", False)

    norm_merchant = re.sub(r"\s+", " ", txn.merchant.strip()).upper()
    is_payout = False
    for name in PAYOUT_MERCHANTS:
        if norm_merchant == name or (
            norm_merchant.startswith(name) and not norm_merchant[len(name) :][:1].isalnum()
        ):
            is_payout = True
            break
    payout_anomaly = is_payout and txn.amount > 0

    # 2. card refund
    if txn.account is Account.CARD and txn.amount < 0:
        return (LineType.REFUND, category, unknown_review)
    # 3. bank deposit
    if txn.account is Account.BANK and txn.amount < 0:
        return (LineType.DEPOSIT, category, unknown_review)
    # 4. purchase
    return (LineType.PURCHASE, category, unknown_review or payout_anomaly)


# -- strategies -------------------------------------------------------------

_merchants = st.one_of(
    st.sampled_from(KNOWN_MERCHANTS),
    st.sampled_from(JUNK_MERCHANTS),
    st.sampled_from(TRANSFER_MERCHANTS),
    # Known name + trailing junk (store numbers etc.)
    st.builds(lambda n, s: f"{n} {s}", st.sampled_from(KNOWN_MERCHANTS), st.text(max_size=6)),
    # Free-form adversarial text (unicode, symbols).
    st.text(max_size=20),
)

_memos = st.one_of(
    st.sampled_from(TRANSFER_MEMOS),
    st.sampled_from(NON_TRANSFER_MEMOS),
    st.text(max_size=30),
)

_amounts = st.decimals(
    min_value=Decimal("-100000"),
    max_value=Decimal("100000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31))

_accounts = st.sampled_from([Account.CARD, Account.BANK])

_ids = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=12,
).map(lambda s: f"txn_{s}")


@st.composite
def transactions(draw) -> Transaction:
    return Transaction(
        id=draw(_ids),
        sync_batch=draw(st.integers(min_value=1, max_value=50)),
        date=draw(_dates),
        account=draw(_accounts),
        merchant=draw(_merchants),
        memo=draw(_memos),
        amount=draw(_amounts),
    )
