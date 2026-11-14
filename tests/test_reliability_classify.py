"""Property-based reliability tests for classification.

The claim under test: classify() never produces a wrong type/category, and in
particular never says 'transfer' when not intended (and never misses a real
transfer). Checked against an INDEPENDENT spec oracle over thousands of
generated transactions, including adversarial merchant/memo strings.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from strategies import expected_classification, transactions

from ledger.constants.enums import LineType
from ledger.stages import classify

HARD = settings(max_examples=2000, deadline=None)


@given(transactions())
@HARD
def test_classify_matches_independent_oracle(txn):
    line = classify(txn)
    exp_type, exp_cat, exp_review = expected_classification(txn)
    assert line.type == exp_type, f"type: {txn.merchant!r}/{txn.memo!r}"
    assert line.category == exp_cat, f"category: {txn.merchant!r}/{txn.memo!r}"
    assert line.needs_review == exp_review, f"review: {txn.merchant!r}/{txn.memo!r}"


@given(transactions())
@HARD
def test_transfer_only_when_intended(txn):
    """The user's explicit worry: no false 'transfer'."""
    line = classify(txn)
    exp_type, _, _ = expected_classification(txn)
    if line.type is LineType.TRANSFER:
        assert exp_type is LineType.TRANSFER, (
            f"false transfer on merchant={txn.merchant!r} memo={txn.memo!r}"
        )
    if exp_type is LineType.TRANSFER:
        assert line.type is LineType.TRANSFER, (
            f"missed transfer on merchant={txn.merchant!r} memo={txn.memo!r}"
        )


@given(transactions())
@HARD
def test_category_is_always_known_or_uncategorized(txn):
    """Category is never garbage: it's either a list category or Uncategorized."""
    from ledger.constants.merchants import MERCHANT_CATEGORIES, UNCATEGORIZED

    valid = set(MERCHANT_CATEGORIES.values()) | {UNCATEGORIZED, "Transfer"}
    assert classify(txn).category in valid


@given(transactions())
@HARD
def test_type_is_always_a_valid_enum(txn):
    assert classify(txn).type in set(LineType)


# A directed battery of near-miss merchant names that must never match a list
# entry by accident (prefix false positives).
@given(
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=500, deadline=None)
def test_no_prefix_false_positive(suffix):
    """A list name immediately followed by an alnum char is a DIFFERENT merchant
    and must not inherit the category."""
    from ledger.stages import categorize

    for name in ["SYSCO", "US FOODS", "ECOLAB", "GUSTO", "INDEED"]:
        glued = name + suffix  # e.g. SYSCOxyz -> not SYSCO
        cat, review = categorize(glued)
        assert cat == "Uncategorized", f"{glued!r} wrongly matched {name!r} -> {cat}"
        assert review is True
