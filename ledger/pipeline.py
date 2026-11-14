"""Compose the stages into one run.

Flow: stream rows -> parse (errors peeled to rejects) -> dedupe (highest batch)
-> classify -> sort -> atomic write. Everything is a generator until the dedupe
map, which is the one stateful stage.

Parallelism: parse+classify are pure per-row work. Above config.parallel_threshold
we run them in a process pool over batches; below it we stay single-process
because pool setup would be slower. The RESULT is identical either way — dedupe
and the final sort are serial and authoritative, so determinism never depends on
worker scheduling.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .config import DEFAULT_CONFIG, Config
from .errors import LedgerError
from .io import (
    checkpoint_store,
    count_data_rows,
    input_fingerprint,
    stream_rows,
    write_ledger,
    write_rejects,
)
from .models import Checkpoint, LedgerLine, RawRow, Transaction
from .stages import classify
from .stages.dedupe import Deduper
from .stages.parse import RowParser

log = logging.getLogger("ledger")

_parser = RowParser()


@dataclass
class RunStats:
    rows_read: int = 0
    rows_emitted: int = 0
    rows_rejected: int = 0
    review_count: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    reject_reasons: dict[str, int] = field(default_factory=dict)
    elapsed_s: float = 0.0


def _batched(rows: Iterable[RawRow], size: int) -> Iterator[list[RawRow]]:
    batch: list[RawRow] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _parse_batch(rows: list[RawRow]) -> tuple[list[Transaction], list[dict]]:
    """Pure worker: parse a batch, returning (transactions, reject_rows).
    Picklable because RowParser is stateless and LedgerError.as_reject_row()
    yields plain dicts."""
    oks: list[Transaction] = []
    rejects: list[dict] = []
    for row in rows:
        try:
            oks.append(_parser.parse(row))
        except LedgerError as e:
            rejects.append(e.as_reject_row())
    return oks, rejects


def _iter_parsed(
    rows: Iterable[RawRow], cfg: Config, use_parallel: bool
) -> Iterator[tuple[list[Transaction], list[dict]]]:
    if not use_parallel:
        for batch in _batched(rows, cfg.batch_size):
            yield _parse_batch(batch)
        return
    workers = cfg.max_workers or max((os.cpu_count() or 2) - 1, 1)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        # map keeps batch order; order doesn't matter for correctness but keeps
        # logs intuitive. Chunk via the generator so we never hold the whole
        # input in memory.
        for result in pool.map(_parse_batch, _batched(rows, cfg.batch_size)):
            yield result


def run(
    input_path: str,
    output_path: str,
    rejects_path: str,
    *,
    cfg: Config = DEFAULT_CONFIG,
    resume: bool = False,
) -> RunStats:
    """Execute a full run and return stats. Raises LedgerError only for fatal,
    whole-run conditions (missing file/columns); per-row problems become
    rejects, never exceptions."""
    start = time.perf_counter()
    stats = RunStats()

    fingerprint = input_fingerprint(input_path)
    cp_path = checkpoint_store.default_path(output_path)

    # Resume handling. The dedupe stage needs a global view of every id, so the
    # read always starts at the top; "resume" here means (a) validate we're
    # continuing the same input via the fingerprint, and (b) skip the expensive
    # pool spin-up decision afresh. Because the final write is idempotent
    # (id-keyed + atomic replace), re-reading a file we'd partly processed
    # before a crash yields byte-identical output — so correctness never depends
    # on resuming at an exact row. A mismatched/corrupt checkpoint => start clean.
    if resume:
        try:
            cp = checkpoint_store.load_for_input(cp_path, fingerprint)
        except LedgerError as e:
            log.warning("%s; starting fresh", e.render())
            cp = None
        if cp is not None:
            log.info(
                "resuming same input (checkpoint at line %d); re-reading from top "
                "to rebuild dedupe state, output is idempotent",
                cp.source_line,
            )

    total = count_data_rows(input_path)
    use_parallel = total >= cfg.parallel_threshold
    if use_parallel:
        log.info("parallel mode: %d rows >= threshold %d", total, cfg.parallel_threshold)

    reject_rows: list[dict] = []

    def record_reject(d: dict) -> None:
        reject_rows.append(d)
        reason = d.get("reason", "unknown")
        stats.reject_reasons[reason] = stats.reject_reasons.get(reason, 0) + 1
        stats.rows_rejected += 1

    deduper = Deduper(
        on_reject=lambda e: record_reject(e.as_reject_row())
    )

    # Stage 1+2: read -> parse -> feed dedupe. Checkpoint periodically so a
    # crash leaves a durable marker (and the fingerprint) for --resume.
    last_line = 0
    rows = stream_rows(input_path)
    for oks, rejects in _iter_parsed(rows, cfg, use_parallel):
        stats.rows_read += len(oks) + len(rejects)
        for d in rejects:
            record_reject(d)
        for txn in oks:
            deduper.add(txn)
            last_line = max(last_line, txn.source_line)
        if stats.rows_read and stats.rows_read % cfg.checkpoint_every < cfg.batch_size:
            checkpoint_store.save(
                cp_path,
                Checkpoint(
                    input_fingerprint=fingerprint,
                    source_line=last_line,
                    byte_offset=0,  # read restarts at top; kept for format stability
                    rows_emitted=0,
                    rows_rejected=stats.rows_rejected,
                ),
            )

    # Stage 3: classify the winners (pure, could be parallelized too; the
    # winner set is already in memory and typically small relative to input).
    lines: list[LedgerLine] = []
    for txn in deduper.winners():
        line = classify(txn)
        lines.append(line)
        stats.type_counts[line.type.value] = (
            stats.type_counts.get(line.type.value, 0) + 1
        )
        if line.needs_review:
            stats.review_count += 1

    # Stage 4: deterministic sort + atomic write (idempotent).
    stats.rows_emitted = write_ledger(output_path, lines)
    write_rejects(rejects_path, reject_rows)

    # A completed run has no partial state to resume from.
    checkpoint_store.clear(cp_path)

    stats.elapsed_s = time.perf_counter() - start
    return stats
