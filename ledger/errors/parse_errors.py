"""Failures that happen while turning a raw feed row into a typed transaction."""

from __future__ import annotations

from .base import LedgerError


class MissingFieldError(LedgerError):
    reason_code = "missing_field"


class MalformedAmountError(LedgerError):
    reason_code = "malformed_amount"


class BadDateError(LedgerError):
    reason_code = "bad_date"


class UnknownAccountError(LedgerError):
    reason_code = "unknown_account"


class NonNumericBatchError(LedgerError):
    reason_code = "non_numeric_batch"
