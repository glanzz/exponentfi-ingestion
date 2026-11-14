"""Account identifiers and the signals that mark a row as a transfer between
the operator's own accounts."""

from __future__ import annotations

import re

VALID_ACCOUNTS: frozenset[str] = frozenset({"card", "bank"})

# A memo that carries a transfer keyword as a whole word. "ACH PAYMENT" matches
# on the word PAYMENT; the merchant-agreement check in classify.py is what
# keeps a real expense (e.g. MAINLINE rent) from being pulled into Transfer.
TRANSFER_MEMO_RE = re.compile(r"\b(TRANSFER|PAYMENT)\b", re.IGNORECASE)

# Merchants/descriptions that are transfer counterparties by their own text,
# independent of memo: moves to/from savings, card payments, the "payment
# received" credit leg.
TRANSFER_MERCHANT_RE = re.compile(
    r"(TRANSFER\s+(TO|FROM)\s+SAVINGS|PAYMENT\s+TO\s+CARD|PAYMENT\s+RECEIVED)",
    re.IGNORECASE,
)
