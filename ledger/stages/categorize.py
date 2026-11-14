"""Merchant -> (category, needs_review).

This is the single seam where a future LLM step would plug in for the
Uncategorized rows. Keep it a pure function of the merchant string. Do not build
the LLM here.

Matching rules:
  - case-insensitive
  - trim and collapse internal whitespace
  - the list name must match at a word boundary (so "SYSCO" does not match a
    hypothetical "SYSCOLOR"); trailing store numbers / junk are fine
  - on overlap, the longest list name wins
"""

from __future__ import annotations

import re
from functools import lru_cache

from ..constants.merchants import MERCHANT_CATEGORIES, UNCATEGORIZED

# Longest names first so the first match is also the most specific.
_SORTED_MERCHANTS = sorted(MERCHANT_CATEGORIES, key=len, reverse=True)

_WS = re.compile(r"\s+")


def _normalize(merchant: str) -> str:
    return _WS.sub(" ", merchant.strip()).upper()


@lru_cache(maxsize=4096)
def _match_merchant(normalized: str) -> str | None:
    for name in _SORTED_MERCHANTS:
        if normalized == name:
            return name
        # Prefix match, but only at a word boundary: the char after the name
        # must not be alphanumeric. "SYSCO PHILA" matches "SYSCO"; "SYSCOLOR"
        # does not.
        if normalized.startswith(name):
            nxt = normalized[len(name)]
            if not nxt.isalnum():
                return name
    return None


def categorize(merchant: str) -> tuple[str, bool]:
    """Return (category, needs_review). Unknown merchant -> Uncategorized,
    needs_review True."""
    name = _match_merchant(_normalize(merchant))
    if name is None:
        return UNCATEGORIZED, True
    return MERCHANT_CATEGORIES[name], False
