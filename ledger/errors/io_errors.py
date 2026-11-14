"""Failures from the I/O edges: reading the feed, resuming, writing output."""

from __future__ import annotations

from .base import LedgerError


class MissingColumnsError(LedgerError):
    """The feed header doesn't have the columns we need. Fatal for the run."""

    reason_code = "missing_columns"


class CheckpointMismatchError(LedgerError):
    """A checkpoint exists but it was written for a different input file.
    Refusing to resume is the safe choice."""

    reason_code = "checkpoint_mismatch"
