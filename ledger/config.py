"""All tunables in one place. Nothing operational should be a literal buried in
the pipeline; it should be here where an operator can find and change it."""

from __future__ import annotations

from dataclasses import dataclass

# Required columns in the input feed.
INPUT_COLUMNS = ("id", "sync_batch", "date", "account", "merchant", "memo", "amount")

# Columns in the output ledger (the current-view projection). The model carries
# more (sync_batch, review_state) but Story 1's CSV is exactly these six.
OUTPUT_COLUMNS = (
    "transaction_id",
    "date",
    "type",
    "category",
    "amount",
    "needs_review",
)

REJECT_COLUMNS = (*INPUT_COLUMNS, "reason", "detail")


@dataclass(frozen=True)
class Config:
    # Parallelism is a scale lever, off by default. Below this many rows we run
    # single-process because spinning up workers would be slower. Benchmarks
    # show the process pool is IPC-bound (parse/classify are cheap per row), so
    # it only helps on very large feeds; keep the threshold high and let serial
    # handle the common case.
    parallel_threshold: int = 2_000_000
    batch_size: int = 10_000
    # 0 -> max(cpu_count()//2 - 1, 1) at runtime: half the cores minus one, to
    # leave headroom and limit pickling contention.
    max_workers: int = 0

    # Checkpoint cadence for resume. Lower = more durable, more I/O.
    checkpoint_every: int = 50_000

    # Above this many unique ids, switch dedupe to the external-sort path
    # instead of the in-memory map. (Hook for scale; the map handles the
    # realistic range.)
    dedupe_inmemory_max_ids: int = 20_000_000


DEFAULT_CONFIG = Config()
