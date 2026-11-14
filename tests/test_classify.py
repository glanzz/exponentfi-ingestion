"""Classify + categorize: one test per type rule and branch, plus the resolved
design edge cases (transfer conflict, payout clawback, unmatched legs)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ledger.constants.enums import Account, LineType, ReviewState
from ledger.models import Transaction
from ledger.stages import categorize, classify


def txn(**overrides) -> Transaction:
    base = dict(
        id="txn_1",
        sync_batch=1,
        date=date(2026, 8, 3),
        account=Account.CARD,
        merchant="SYSCO PHILA 8827",
        memo="SYSCO PHILA 8827",
        amount=Decimal("100.00"),
    )
    base.update(overrides)
    return Transaction(**base)


# -- categorize ------------------------------------------------------------


def test_categorize_known():
    assert categorize("SYSCO PHILA 8827") == ("Food & beverage", False)


def test_categorize_unknown():
    cat, review = categorize("AMZN MKTP US*2K4X9")
    assert cat == "Uncategorized"
    assert review is True


def test_categorize_case_and_whitespace():
    assert categorize("  sysco   phila  8827 ") == ("Food & beverage", False)


def test_categorize_longest_match_wins():
    # US FOODS must not be shadowed by a shorter overlapping name; here just
    # confirm the full specific name resolves.
    assert categorize("RESTAURANT DEPOT 0093") == ("Food & beverage", False)


def test_categorize_word_boundary_no_false_prefix():
    # "SYSCOLOR" must NOT match "SYSCO".
    cat, review = categorize("SYSCOLOR PAINT 12")
    assert cat == "Uncategorized"
    assert review is True


# -- type rules ------------------------------------------------------------


def test_purchase_default():
    line = classify(txn(account=Account.CARD, amount=Decimal("100.00")))
    assert line.type is LineType.PURCHASE
    assert line.category == "Food & beverage"
    assert line.needs_review is False


def test_card_refund_known_merchant():
    line = classify(
        txn(account=Account.CARD, amount=Decimal("-59.99"), merchant="HOME DEPOT #4102",
            memo="HOME DEPOT RETURN")
    )
    assert line.type is LineType.REFUND
    assert line.category == "Repairs & maintenance"
    assert line.needs_review is False


def test_card_refund_unknown_merchant():
    line = classify(
        txn(account=Account.CARD, amount=Decimal("-41.99"),
            merchant="AMZN MKTP US*7Q1P2", memo="AMAZON MARKETPLACE REFUND")
    )
    assert line.type is LineType.REFUND
    assert line.category == "Uncategorized"
    assert line.needs_review is True


def test_bank_deposit_known_merchant():
    line = classify(
        txn(account=Account.BANK, amount=Decimal("-2210.45"),
            merchant="DOORDASH PAYOUT", memo="DOORDASH INC PAYOUT")
    )
    assert line.type is LineType.DEPOSIT
    assert line.category == "Delivery sales"
    assert line.needs_review is False


def test_bank_deposit_unknown_merchant():
    line = classify(
        txn(account=Account.BANK, amount=Decimal("-500.00"),
            merchant="MYSTERY CREDIT", memo="REFUND")
    )
    assert line.type is LineType.DEPOSIT
    assert line.category == "Uncategorized"
    assert line.needs_review is True


# -- transfers -------------------------------------------------------------


def test_transfer_card_payment_leg():
    # bank side: ONLINE PAYMENT TO CARD
    line = classify(
        txn(account=Account.BANK, amount=Decimal("4850.00"),
            merchant="ONLINE PAYMENT TO CARD 4421",
            memo="ONLINE PAYMENT TO CARD 4421")
    )
    assert line.type is LineType.TRANSFER
    assert line.category == "Transfer"
    assert line.needs_review is False


def test_transfer_payment_received_leg():
    line = classify(
        txn(account=Account.CARD, amount=Decimal("-4850.00"),
            merchant="PAYMENT RECEIVED", memo="ONLINE PAYMENT - THANK YOU")
    )
    assert line.type is LineType.TRANSFER
    assert line.category == "Transfer"


def test_transfer_savings_legs():
    out = classify(
        txn(account=Account.BANK, amount=Decimal("10000.00"),
            merchant="TRANSFER TO SAVINGS 8810", memo="ONLINE TRANSFER TO SAVINGS 8810")
    )
    back = classify(
        txn(account=Account.BANK, amount=Decimal("-5000.00"),
            merchant="TRANSFER FROM SAVINGS 8810",
            memo="ONLINE TRANSFER FROM SAVINGS 8810")
    )
    assert out.type is LineType.TRANSFER
    assert back.type is LineType.TRANSFER


def test_transfer_conflict_goes_to_review():
    # MAINLINE rent paid by ACH: memo has PAYMENT but merchant is on the
    # expense list. Must NOT become a transfer; must go to review.
    line = classify(
        txn(account=Account.BANK, amount=Decimal("6500.00"),
            merchant="MAINLINE PROPERTIES LLC",
            memo="ACH PAYMENT MAINLINE PROPERTIES")
    )
    assert line.type is not LineType.TRANSFER
    assert line.needs_review is True
    assert line.review_state is ReviewState.PENDING_REVIEW


def test_normal_merchant_memo_with_payment_word_not_swallowed_when_on_list():
    # GUSTO PAYROLL does not contain the whole word PAYMENT, so it is a normal
    # purchase, not a transfer and not a conflict.
    line = classify(
        txn(account=Account.BANK, amount=Decimal("14210.66"),
            merchant="GUSTO", memo="GUSTO PAYROLL")
    )
    assert line.type is LineType.PURCHASE
    assert line.category == "Payroll"
    assert line.needs_review is False


# -- payout clawback -------------------------------------------------------


def test_positive_payout_flagged():
    # A positive TOAST PAYOUT (clawback) is a purchase by sign, but abnormal.
    line = classify(
        txn(account=Account.BANK, amount=Decimal("500.00"),
            merchant="TOAST PAYOUT", memo="TOAST CLAWBACK")
    )
    assert line.type is LineType.PURCHASE
    assert line.needs_review is True


def test_normal_negative_payout_not_flagged():
    line = classify(
        txn(account=Account.BANK, amount=Decimal("-6120.30"),
            merchant="TOAST PAYOUT", memo="TOAST INC DAILY PAYOUT")
    )
    assert line.type is LineType.DEPOSIT
    assert line.needs_review is False
