"""The feed row exactly as received: every field a string, nothing validated.

Keeping the raw row around means a rejected row can be written back out with its
original values intact.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawRow:
    id: str
    sync_batch: str
    date: str
    account: str
    merchant: str
    memo: str
    amount: str
    # 1-based line number in the source file, for logging and checkpoints.
    source_line: int = 0

    @classmethod
    def from_mapping(cls, m: Mapping[str, str], source_line: int = 0) -> RawRow:
        """Build from a csv.DictReader row. Missing keys become empty strings so
        the parse stage (not this constructor) owns the 'missing field' decision
        with full context."""

        def get(k: str) -> str:
            v = m.get(k)
            return v.strip() if v is not None else ""

        return cls(
            id=get("id"),
            sync_batch=get("sync_batch"),
            date=get("date"),
            account=get("account"),
            merchant=get("merchant"),
            memo=get("memo"),
            amount=get("amount"),
            source_line=source_line,
        )

    def as_dict(self) -> dict[str, str]:
        """Original columns only (no source_line) for the rejects file."""
        return {
            "id": self.id,
            "sync_batch": self.sync_batch,
            "date": self.date,
            "account": self.account,
            "merchant": self.merchant,
            "memo": self.memo,
            "amount": self.amount,
        }
