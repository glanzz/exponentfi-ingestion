"""The merchant -> category list, as data.

Edit this list to add merchants; no logic lives here. The matcher in
stages/categorize.py does case-insensitive, whitespace-normalized,
word-boundary prefix matching and prefers the longest match on overlap.
"""

from __future__ import annotations

# Order does not matter; the matcher resolves overlaps by longest name.
MERCHANT_CATEGORIES: dict[str, str] = {
    "SYSCO": "Food & beverage",
    "US FOODS": "Food & beverage",
    "RESTAURANT DEPOT": "Food & beverage",
    "METRO GAS & ELECTRIC": "Utilities",
    "CITY WATER DEPT": "Utilities",
    "COMCAST BUSINESS": "Utilities",
    "HOME DEPOT": "Repairs & maintenance",
    "ECOLAB": "Cleaning & supplies",
    "WEBSTAURANT STORE": "Smallwares & supplies",
    "GUSTO": "Payroll",
    "INDEED": "Hiring",
    "7SHIFTS": "Software",
    "MAINLINE PROPERTIES": "Rent",
    "TOAST PAYOUT": "Card sales",
    "DOORDASH PAYOUT": "Delivery sales",
    "UBER EATS PAYOUT": "Delivery sales",
}

UNCATEGORIZED = "Uncategorized"

# Merchants whose normal amount is money coming in (negative). A positive
# amount on one of these is abnormal (e.g. a clawback) and gets flagged for
# review rather than booked silently.
PAYOUT_MERCHANTS: frozenset[str] = frozenset(
    {"TOAST PAYOUT", "DOORDASH PAYOUT", "UBER EATS PAYOUT"}
)
