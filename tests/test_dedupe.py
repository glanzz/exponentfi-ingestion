"""Dedupe: highest batch wins regardless of arrival order; same-batch dup is
rejected deterministically."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ledger.constants.enums import Account
from ledger.errors import DuplicateInBatchError
from ledger.models import Transaction
from ledger.stages import dedupe
from ledger.stages.dedupe import Deduper


def txn(id_, batch, amount) -> Transaction:
    return Transaction(
        id=id_,
        sync_batch=batch,
        date=date(2026, 8, 10),
        account=Account.CARD,
        merchant="SHELL OIL 57318",
        memo="SHELL",
        amount=Decimal(amount),
    )


def test_higher_batch_wins():
    winners = dedupe([txn("a", 1, "1.00"), txn("a", 2, "62.40")])
    assert len(winners) == 1
    assert winners[0].sync_batch == 2
    assert winners[0].amount == Decimal("62.40")


def test_lower_batch_arriving_later_does_not_override():
    # batch 2 first, then batch 1 — batch 2 must still win
    winners = dedupe([txn("a", 2, "62.40"), txn("a", 1, "1.00")])
    assert winners[0].sync_batch == 2


def test_batch_10_beats_batch_9():
    winners = dedupe([txn("a", 9, "9.00"), txn("a", 10, "10.00")])
    assert winners[0].sync_batch == 10


def test_distinct_ids_all_kept():
    winners = dedupe([txn("a", 1, "1"), txn("b", 1, "2"), txn("c", 1, "3")])
    assert {w.id for w in winners} == {"a", "b", "c"}


def test_same_batch_duplicate_rejected_and_last_wins():
    rejects = []
    d = Deduper(on_reject=rejects.append)
    d.add(txn("a", 1, "1.00"))
    d.add(txn("a", 1, "2.00"))
    winners = list(d.winners())
    assert len(winners) == 1
    assert winners[0].amount == Decimal("2.00")  # last in file wins
    assert len(rejects) == 1
    assert isinstance(rejects[0], DuplicateInBatchError)


def test_order_independence():
    import random

    rows = [txn("a", 1, "1"), txn("a", 2, "2"), txn("b", 1, "3"), txn("b", 3, "4")]
    shuffled = rows[:]
    random.shuffle(shuffled)
    a = {(w.id, w.sync_batch) for w in dedupe(rows)}
    b = {(w.id, w.sync_batch) for w in dedupe(shuffled)}
    assert a == b == {("a", 2), ("b", 3)}
