"""The output record.

The CSV view projects only the six required Story-1 columns. The model also
carries sync_batch and review_state so the Story-3 review queue is a column
addition, not a schema migration (see the architecture doc, v2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

from ..constants.enums import LineType, ReviewState


def _format_amount(value: Decimal) -> str:
    """Exactly two decimals, and never '-0.00'."""
    quantized = value.quantize(Decimal("0.01"))
    if quantized == 0:
        quantized = quantized.copy_abs()  # collapse -0.00 -> 0.00
    return f"{quantized:.2f}"


@dataclass(frozen=True, slots=True)
class LedgerLine:
    transaction_id: str
    date: Date
    type: LineType
    category: str
    amount: Decimal
    needs_review: bool
    # Forward-compat fields (not in the Story-1 CSV projection).
    sync_batch: int = 0
    review_state: ReviewState = ReviewState.AUTO

    def as_output_row(self) -> dict[str, str]:
        """The six Story-1 columns, every value a string, canonically formatted."""
        return {
            "transaction_id": self.transaction_id,
            "date": self.date.isoformat(),
            "type": self.type.value,
            "category": self.category,
            "amount": _format_amount(self.amount),
            "needs_review": "true" if self.needs_review else "false",
        }

    def sort_key(self) -> tuple[str, str]:
        """Deterministic output order: date, then id. Reruns diff cleanly."""
        return (self.date.isoformat(), self.transaction_id)
