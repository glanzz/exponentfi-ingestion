"""Base error for everything the pipeline can reject.

Every failure mode subclasses LedgerError. The base owns the formatting so
every rejection prints the same way and serializes to rejected_rows.csv the
same way; subclasses only supply a stable reason_code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class LedgerError(Exception):
    """A row we could not process. Carries enough context to log it and to
    write it to the failures file without losing the original data."""

    # Stable, machine-readable. Goes in the CSV; don't change casually.
    reason_code: str = "unknown"

    def __init__(
        self,
        *,
        row_id: str | None = None,
        batch: str | int | None = None,
        detail: str | None = None,
        raw: Mapping[str, Any] | None = None,
    ) -> None:
        self.row_id = row_id
        self.batch = batch
        self.detail = detail
        # Keep a copy so a later mutation of the source dict can't change what
        # we rejected.
        self.raw = dict(raw) if raw is not None else None
        super().__init__(self.render())

    def render(self) -> str:
        """One consistent human-readable line. Safe to hand to a logger."""
        loc = f"[{self.row_id or '?'}@batch {self.batch if self.batch is not None else '?'}]"
        tail = f": {self.detail}" if self.detail else ""
        return f"{loc} {self.reason_code}{tail}"

    def as_reject_row(self) -> dict[str, Any]:
        """A dict suitable for a row in rejected_rows.csv: the original fields
        plus why we rejected it."""
        base = dict(self.raw) if self.raw else {}
        base["reason"] = self.reason_code
        base["detail"] = self.detail or ""
        return base
