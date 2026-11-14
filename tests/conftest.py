"""Shared fixtures and path helpers for the test suite."""

from __future__ import annotations

import os

import pytest

HERE = os.path.dirname(__file__)
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "data")


@pytest.fixture
def transactions_csv() -> str:
    return os.path.join(DATA, "transactions.csv")


@pytest.fixture
def expected_first_15_csv() -> str:
    return os.path.join(DATA, "expected_first_15.csv")
