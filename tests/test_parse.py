"""Parse stage: one test per failure mode plus the messy-amount cases."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ledger.constants.enums import Account
from ledger.errors import (
    BadDateError,
    MalformedAmountError,
    MissingFieldError,
    NonNumericBatchError,
    UnknownAccountError,
)
from ledger.models import RawRow
from ledger.stages import RowParser


def row(**overrides) -> RawRow:
    base = dict(
        id="txn_1",
        sync_batch="1",
        date="2026-08-03",
        account="card",
        merchant="SYSCO PHILA 8827",
        memo="SYSCO PHILA 8827",
        amount="1842.17",
    )
    base.update(overrides)
    return RawRow.from_mapping(base, source_line=2)


@pytest.fixture
def parser() -> RowParser:
    return RowParser()


def test_happy_path(parser):
    txn = parser.parse(row())
    assert txn.id == "txn_1"
    assert txn.sync_batch == 1
    assert txn.date == date(2026, 8, 3)
    assert txn.account is Account.CARD
    assert txn.amount == Decimal("1842.17")


def test_missing_required_field(parser):
    with pytest.raises(MissingFieldError):
        parser.parse(row(id=""))


def test_missing_amount(parser):
    with pytest.raises(MissingFieldError):
        parser.parse(row(amount=""))


def test_bad_date(parser):
    with pytest.raises(BadDateError):
        parser.parse(row(date="08/03/2026"))


def test_unknown_account(parser):
    with pytest.raises(UnknownAccountError):
        parser.parse(row(account="savings"))


def test_non_numeric_batch(parser):
    with pytest.raises(NonNumericBatchError):
        parser.parse(row(sync_batch="latest"))


def test_batch_parsed_numerically(parser):
    # The classic trap: "10" must be greater than "9".
    assert parser.parse(row(sync_batch="10")).sync_batch == 10
    assert parser.parse(row(sync_batch="9")).sync_batch == 9
    assert (
        parser.parse(row(sync_batch="10")).sync_batch > parser.parse(row(sync_batch="9")).sync_batch
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,234.56", Decimal("1234.56")),
        ("(1,234.56)", Decimal("-1234.56")),
        ("-0.00", Decimal("0.00")),
        ("  42.00  ", Decimal("42.00")),
        ("-59.99", Decimal("-59.99")),
    ],
)
def test_messy_amounts(parser, raw, expected):
    assert parser.parse(row(amount=raw)).amount == expected


def test_minus_zero_is_not_negative(parser):
    amt = parser.parse(row(amount="-0.00")).amount
    assert amt == Decimal("0")
    assert not (amt < 0)


@pytest.mark.parametrize("bad", ["abc", "", "   ", "-", "$"])
def test_malformed_amount_rejected(parser, bad):
    with pytest.raises((MalformedAmountError, MissingFieldError)):
        parser.parse(row(amount=bad))


@pytest.mark.parametrize("bad", ["NaN", "nan", "Infinity", "inf", "-inf", "+Inf"])
def test_non_finite_amount_rejected(parser, bad):
    # Decimal() happily parses these; they must NOT enter the ledger (NaN also
    # breaks amount < 0 comparisons downstream).
    with pytest.raises(MalformedAmountError):
        parser.parse(row(amount=bad))


def test_absurd_magnitude_rejected(parser):
    with pytest.raises(MalformedAmountError):
        parser.parse(row(amount="1E999999"))


def test_exact_decimal_math(parser):
    a = parser.parse(row(amount="0.10")).amount
    b = parser.parse(row(amount="0.20")).amount
    assert a + b == Decimal("0.30")


def test_reject_row_preserves_original(parser):
    try:
        parser.parse(row(amount="garbage", id="txn_99"))
    except MalformedAmountError as e:
        rr = e.as_reject_row()
        assert rr["id"] == "txn_99"
        assert rr["amount"] == "garbage"
        assert rr["reason"] == "malformed_amount"
    else:
        pytest.fail("expected MalformedAmountError")
