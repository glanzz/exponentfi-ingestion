"""Property-based reliability tests for dedupe.

Claim: dedupe always keeps the version from the TRUE highest sync_batch, emits
exactly one line per id, and is independent of input order.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from strategies import transactions

from ledger.models import Transaction
from ledger.stages.dedupe import Deduper, dedupe

HARD = settings(max_examples=2000, deadline=None)


@given(st.lists(transactions(), min_size=1, max_size=60))
@HARD
def test_winner_has_max_batch_per_id(rows):
    winners = {t.id: t for t in dedupe(rows)}
    # Independent oracle: the max batch seen per id.
    expected_max = {}
    for t in rows:
        expected_max[t.id] = max(expected_max.get(t.id, t.sync_batch), t.sync_batch)
    assert set(winners) == set(expected_max)
    for tid, t in winners.items():
        assert t.sync_batch == expected_max[tid], (
            f"id {tid}: kept batch {t.sync_batch}, max was {expected_max[tid]}"
        )


@given(st.lists(transactions(), min_size=0, max_size=60))
@HARD
def test_output_count_equals_unique_ids(rows):
    winners = dedupe(rows)
    assert len(winners) == len({t.id for t in rows})
    # No duplicate ids in the output.
    out_ids = [t.id for t in winners]
    assert len(out_ids) == len(set(out_ids))


@given(st.lists(transactions(), min_size=1, max_size=60), st.randoms(use_true_random=False))
@HARD
def test_dedupe_is_order_independent(rows, rnd):
    shuffled = rows[:]
    rnd.shuffle(shuffled)
    a = {(t.id, t.sync_batch) for t in dedupe(rows)}
    b = {(t.id, t.sync_batch) for t in dedupe(shuffled)}
    assert a == b


@given(st.lists(transactions(), min_size=1, max_size=60))
@HARD
def test_lower_batch_never_overrides_higher(rows):
    """Even if a lower batch arrives LAST, it must not win."""
    # Force a worst case: append a low-batch duplicate of every id at the end.
    tail = [
        type(t)(
            id=t.id,
            sync_batch=0,  # lower than any generated batch (>=1)
            date=t.date,
            account=t.account,
            merchant=t.merchant,
            memo=t.memo,
            amount=t.amount,
        )
        for t in rows
    ]
    winners = {t.id: t for t in dedupe(rows + tail)}
    for t in winners.values():
        assert t.sync_batch >= 1, f"id {t.id}: a batch-0 straggler overrode a real row"


@given(st.lists(transactions(), min_size=1, max_size=40))
@HARD
def test_same_batch_duplicate_keeps_exactly_one_and_logs(rows):
    """A same-id-same-batch collision keeps one winner and rejects the loser."""
    target = rows[0]
    # The collision only happens at the id's MAX batch (a lower batch is dropped
    # as a stale re-sync, not a same-batch dup). Force the duplicate at the max
    # batch seen for this id so a collision is guaranteed.
    max_batch = max(t.sync_batch for t in rows if t.id == target.id)
    dup = Transaction(
        id=target.id,
        sync_batch=max_batch,
        date=target.date,
        account=target.account,
        merchant=target.merchant,
        memo=target.memo,
        amount=target.amount,
    )
    rejects = []
    d = Deduper(on_reject=rejects.append)
    for t in rows:
        d.add(t)
    d.add(dup)  # exact same id + (max) batch again -> guaranteed collision
    winners = {t.id for t in d.winners()}
    assert dup.id in winners
    assert len(rejects) >= 1  # the collision must be logged, never silently lost
