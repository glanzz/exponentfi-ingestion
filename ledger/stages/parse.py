"""Turn a RawRow into a typed Transaction, or raise a specific LedgerError.

Each failure mode is its own method so it can be tested and reasoned about in
isolation. parse() orchestrates them in a fixed order (cheap/structural checks
before expensive ones) and attaches row context to whatever is raised.
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime
from decimal import Decimal, InvalidOperation

from ..constants.accounts import VALID_ACCOUNTS
from ..constants.enums import Account
from ..errors import (
    BadDateError,
    MalformedAmountError,
    MissingFieldError,
    NonNumericBatchError,
    UnknownAccountError,
)
from ..models import RawRow, Transaction

# Required to produce a line at all. memo may be blank; amount 0 is valid.
_REQUIRED_FIELDS = ("id", "sync_batch", "date", "account", "amount")

# Strip currency noise before parsing a money value.
_CURRENCY_STRIP = re.compile(r"[,$\s]")


class RowParser:
    """Stateless; one instance is fine to reuse across rows (and to pickle for
    the process pool)."""

    def parse(self, row: RawRow) -> Transaction:
        self._require_fields(row)
        batch = self._parse_batch(row)
        when = self._parse_date(row)
        account = self._parse_account(row)
        amount = self._parse_amount(row)
        return Transaction(
            id=row.id,
            sync_batch=batch,
            date=when,
            account=account,
            merchant=row.merchant,
            memo=row.memo,
            amount=amount,
            source_line=row.source_line,
        )

    # -- one function per failure mode --------------------------------------

    def _require_fields(self, row: RawRow) -> None:
        missing = [f for f in _REQUIRED_FIELDS if not getattr(row, f)]
        if missing:
            raise MissingFieldError(
                row_id=row.id or None,
                batch=row.sync_batch or None,
                detail=f"empty required field(s): {', '.join(missing)}",
                raw=row.as_dict(),
            )

    def _parse_batch(self, row: RawRow) -> int:
        # sync_batch as a string sorts "9" > "10"; parse numerically so the
        # highest batch actually wins. Accept a plain integer here; a date-style
        # batch would be handled upstream, but this feed uses integers.
        text = row.sync_batch.strip()
        try:
            return int(text)
        except (ValueError, TypeError):
            raise NonNumericBatchError(
                row_id=row.id,
                batch=row.sync_batch,
                detail=f"sync_batch is not an integer: {text!r}",
                raw=row.as_dict(),
            )

    def _parse_date(self, row: RawRow) -> Date:
        text = row.date.strip()
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise BadDateError(
                row_id=row.id,
                batch=row.sync_batch,
                detail=f"date not YYYY-MM-DD: {text!r}",
                raw=row.as_dict(),
            )

    def _parse_account(self, row: RawRow) -> Account:
        text = row.account.strip().lower()
        if text not in VALID_ACCOUNTS:
            raise UnknownAccountError(
                row_id=row.id,
                batch=row.sync_batch,
                detail=f"account not one of {sorted(VALID_ACCOUNTS)}: {row.account!r}",
                raw=row.as_dict(),
            )
        return Account(text)

    def _parse_amount(self, row: RawRow) -> Decimal:
        raw = row.amount.strip()
        text = raw
        # Accounting negatives: (1,234.56) == -1234.56
        negative = text.startswith("(") and text.endswith(")")
        if negative:
            text = text[1:-1]
        text = _CURRENCY_STRIP.sub("", text)
        if text in ("", "-", "+"):
            raise MalformedAmountError(
                row_id=row.id,
                batch=row.sync_batch,
                detail=f"amount is blank or non-numeric: {raw!r}",
                raw=row.as_dict(),
            )
        try:
            value = Decimal(text)
        except InvalidOperation:
            raise MalformedAmountError(
                row_id=row.id,
                batch=row.sync_batch,
                detail=f"amount is not a number: {raw!r}",
                raw=row.as_dict(),
            )
        # Decimal() accepts NaN / Infinity. Those are not money: reject the row
        # rather than let a non-finite value into the ledger (NaN also poisons
        # the amount < 0 comparisons the classifier relies on). Also bound the
        # magnitude so an absurd exponent can't slip through as "finite".
        if not value.is_finite() or abs(value.adjusted()) > 18:
            raise MalformedAmountError(
                row_id=row.id,
                batch=row.sync_batch,
                detail=f"amount is not a finite, in-range number: {raw!r}",
                raw=row.as_dict(),
            )
        if negative:
            value = -value
        # Normalize -0.00 to 0.00 at the value level too.
        if value == 0:
            value = value.copy_abs()
        return value
