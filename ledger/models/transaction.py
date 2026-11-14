"""A validated, typed transaction. Produced by the parse stage; consumed by
dedupe and classify."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

from ..constants.enums import Account


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    sync_batch: int  # parsed numerically so 10 > 9
    date: Date
    account: Account
    merchant: str
    memo: str
    amount: Decimal
    source_line: int = 0

    @property
    def dedupe_key(self) -> str:
        return self.id
