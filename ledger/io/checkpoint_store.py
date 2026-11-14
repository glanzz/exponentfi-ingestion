"""Load, save, and clear the resume checkpoint.

The checkpoint is written atomically so a crash mid-write can't corrupt it. On
resume we refuse to continue against a different input (fingerprint mismatch) —
stitching two feeds together would silently corrupt the ledger.
"""

from __future__ import annotations

import json
import os
import tempfile

from ..errors import CheckpointMismatchError
from ..models import Checkpoint


def default_path(output_path: str) -> str:
    return output_path + ".checkpoint.json"


def save(path: str, checkpoint: Checkpoint) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_json(), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(path: str) -> Checkpoint | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return Checkpoint.from_json(json.load(f))
    except (json.JSONDecodeError, KeyError, ValueError):
        # A corrupt checkpoint is treated as no checkpoint: start clean rather
        # than guess.
        return None


def load_for_input(path: str, expected_fingerprint: str) -> Checkpoint | None:
    """Load only if it belongs to this input; otherwise raise so the caller can
    decide (the CLI turns this into 'starting fresh')."""
    cp = load(path)
    if cp is None:
        return None
    if cp.input_fingerprint != expected_fingerprint:
        raise CheckpointMismatchError(
            detail="checkpoint was written for a different input file; not resuming"
        )
    return cp


def clear(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
