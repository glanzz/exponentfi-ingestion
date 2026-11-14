"""Resume state. Serialized to checkpoint.json between flushes."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Checkpoint:
    # Fingerprint of the input we were processing. Resuming against a different
    # input is refused.
    input_fingerprint: str
    # Last source line durably processed and flushed.
    source_line: int
    # Byte offset in the input for O(1) seek-resume on a plain file.
    byte_offset: int
    rows_emitted: int
    rows_rejected: int

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> Checkpoint:
        return cls(
            input_fingerprint=d["input_fingerprint"],
            source_line=int(d["source_line"]),
            byte_offset=int(d["byte_offset"]),
            rows_emitted=int(d["rows_emitted"]),
            rows_rejected=int(d["rows_rejected"]),
        )
