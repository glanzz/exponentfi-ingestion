"""Failures surfaced by the dedupe stage."""

from __future__ import annotations

from .base import LedgerError


class DuplicateInBatchError(LedgerError):
    """Same id, same batch, more than once. We keep one deterministically and
    reject the loser so the collision is visible rather than silent."""

    reason_code = "duplicate_in_batch"
