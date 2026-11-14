"""Collapse re-synced rows to one per id, keeping the highest sync_batch.

This is the only stateful stage. "Keep highest batch" is associative and
order-independent, which is what makes shuffled input produce identical output.

Within a single batch a duplicate id is a feed bug: we keep the last occurrence
in file order (deterministic) and hand the loser back as a DuplicateInBatchError
so it lands in rejected_rows.csv rather than disappearing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from ..errors import DuplicateInBatchError
from ..models import Transaction


class Deduper:
    """In-memory dedupe. Feed it transactions; drain winners at the end.

    For id cardinality beyond RAM, the external-sort path (sort by id,batch desc
    then streaming group-by) produces the identical result; this class covers
    the realistic range. See config.dedupe_inmemory_max_ids.
    """

    def __init__(self, on_reject: Callable[[DuplicateInBatchError], None] | None = None):
        # id -> winning Transaction so far
        self._best: dict[str, Transaction] = {}
        self._on_reject = on_reject

    def add(self, txn: Transaction) -> None:
        prev = self._best.get(txn.id)
        if prev is None:
            self._best[txn.id] = txn
            return
        if txn.sync_batch > prev.sync_batch:
            self._best[txn.id] = txn
        elif txn.sync_batch < prev.sync_batch:
            pass  # older batch arriving later never overrides
        else:
            # Same id, same batch: later-in-file wins, loser is rejected.
            self._reject(prev)
            self._best[txn.id] = txn

    def _reject(self, loser: Transaction) -> None:
        if self._on_reject is None:
            return
        self._on_reject(
            DuplicateInBatchError(
                row_id=loser.id,
                batch=loser.sync_batch,
                detail=f"duplicate id within batch {loser.sync_batch}; superseded "
                f"by a later row in the same batch",
            )
        )

    def winners(self) -> Iterator[Transaction]:
        return iter(self._best.values())

    @property
    def unique_count(self) -> int:
        return len(self._best)


def dedupe(
    transactions: Iterable[Transaction],
    on_reject: Callable[[DuplicateInBatchError], None] | None = None,
) -> list[Transaction]:
    """Convenience wrapper: consume a stream, return the winners as a list."""
    d = Deduper(on_reject=on_reject)
    for txn in transactions:
        d.add(txn)
    return list(d.winners())
