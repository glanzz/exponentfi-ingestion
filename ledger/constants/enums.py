"""Enumerations shared across the pipeline. str-based so they serialize to the
output CSV as their literal value with no extra work."""

from __future__ import annotations

from enum import Enum


class LineType(str, Enum):
    PURCHASE = "purchase"
    REFUND = "refund"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"


class ReviewState(str, Enum):
    """Where a line sits in the review lifecycle. Story 1 only ever emits AUTO
    or PENDING_REVIEW; REVIEWED exists so the model is forward-compatible with
    the Story 3 review queue without a schema change."""

    AUTO = "auto"
    PENDING_REVIEW = "pending_review"
    REVIEWED = "reviewed"


class Account(str, Enum):
    CARD = "card"
    BANK = "bank"
