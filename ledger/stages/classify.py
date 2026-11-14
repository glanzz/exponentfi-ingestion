"""Transaction -> LedgerLine.

Type decision order (matches the architecture doc and the resolved design
decisions):

  1. Transfer, with the memo+merchant agreement check:
       - transfer signal present AND merchant on the expense list -> CONFLICT:
         Uncategorized, needs_review=True (e.g. MAINLINE "ACH PAYMENT")
       - transfer signal present AND merchant not on the list -> transfer
  2. Card + amount < 0 (and not a transfer) -> refund (same category a purchase
     would get; unknown merchant still refund but Uncategorized/review)
  3. Bank + amount < 0 (and not a transfer) -> deposit
  4. Otherwise -> purchase

Extra safety flags from the resolved design:
  - a positive amount on a payout merchant (a clawback) -> needs_review
"""

from __future__ import annotations

from decimal import Decimal

from ..constants.accounts import TRANSFER_MEMO_RE, TRANSFER_MERCHANT_RE
from ..constants.enums import Account, LineType, ReviewState
from ..constants.merchants import PAYOUT_MERCHANTS, UNCATEGORIZED
from ..models import LedgerLine, Transaction
from .categorize import _match_merchant, _normalize, categorize

_ZERO = Decimal("0")


def _has_transfer_signal(txn: Transaction) -> bool:
    return bool(TRANSFER_MEMO_RE.search(txn.memo) or TRANSFER_MERCHANT_RE.search(txn.merchant))


def _is_payout_merchant(txn: Transaction) -> bool:
    return _match_merchant(_normalize(txn.merchant)) in PAYOUT_MERCHANTS


def classify(txn: Transaction) -> LedgerLine:
    category, needs_review = categorize(txn.merchant)
    on_expense_list = category != UNCATEGORIZED

    def line(
        line_type: LineType,
        cat: str,
        review: bool,
        state: ReviewState = ReviewState.AUTO,
    ) -> LedgerLine:
        return LedgerLine(
            transaction_id=txn.id,
            date=txn.date,
            type=line_type,
            category=cat,
            amount=txn.amount,
            needs_review=review,
            sync_batch=txn.sync_batch,
            review_state=state,
        )

    # 1. Transfer / conflict.
    if _has_transfer_signal(txn):
        if on_expense_list:
            # Memo says "transfer", merchant says it's a real expense. Don't
            # guess; send it to a human. (e.g. MAINLINE rent paid by ACH.)
            return line(
                LineType.PURCHASE,
                UNCATEGORIZED,
                review=True,
                state=ReviewState.PENDING_REVIEW,
            )
        return line(LineType.TRANSFER, "Transfer", review=False)

    # Payout clawback: positive amount where we expect negative. Still follows
    # the sign rules below, but flag it.
    payout_anomaly = _is_payout_merchant(txn) and txn.amount > _ZERO

    # 2. Card refund.
    if txn.account is Account.CARD and txn.amount < _ZERO:
        return line(LineType.REFUND, category, review=needs_review)

    # 3. Bank deposit.
    if txn.account is Account.BANK and txn.amount < _ZERO:
        return line(LineType.DEPOSIT, category, review=needs_review)

    # 4. Purchase (default).
    review = needs_review or payout_anomaly
    return line(LineType.PURCHASE, category, review=review)
