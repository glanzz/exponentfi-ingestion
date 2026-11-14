"""Generate a large, realistic transaction feed for load testing.

Usage:
    python scripts/generate_feed.py 1000000 -o data/transactions_1M.csv

Produces a feed with a mix of merchants (known, unknown, transfer legs), ~20% of
ids re-syncing in a later batch (pending -> posted), messy amounts, and a small
fraction of malformed rows so the reject path gets exercised. Deterministic for a
given seed, so reruns produce the same file.
"""

from __future__ import annotations

import argparse
import csv

MERCHANTS = [
    ("SYSCO PHILA 8827", "SYSCO PHILA 8827", "card"),
    ("US FOODS 2201", "US FOODS 2201", "card"),
    ("HOME DEPOT #4102", "HOME DEPOT #4102", "card"),
    ("ECOLAB 7710", "ECOLAB 7710", "card"),
    ("WEBSTAURANT STORE", "WEBSTAURANT STORE", "card"),
    ("AMZN MKTP US*2K4X9", "AMAZON MARKETPLACE", "card"),  # unknown -> review
    ("TOAST PAYOUT", "TOAST INC DAILY PAYOUT", "bank"),  # deposit
    ("DOORDASH PAYOUT", "DOORDASH INC PAYOUT", "bank"),
    ("GUSTO", "GUSTO PAYROLL", "bank"),  # purchase, NOT transfer
    ("MAINLINE PROPERTIES LLC", "ACH PAYMENT MAINLINE PROPERTIES", "bank"),  # conflict
    ("ONLINE PAYMENT TO CARD 4421", "ONLINE PAYMENT TO CARD 4421", "bank"),  # transfer
    ("PAYMENT RECEIVED", "ONLINE PAYMENT - THANK YOU", "card"),  # transfer
    ("TRANSFER TO SAVINGS 8810", "ONLINE TRANSFER TO SAVINGS 8810", "bank"),
]


def _lcg(seed: int):
    s = seed
    while True:
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        yield s


def generate(path: str, n_rows: int, seed: int = 7) -> None:
    rng = _lcg(seed)
    cols = ["id", "sync_batch", "date", "account", "merchant", "memo", "amount"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(n_rows):
            merchant, memo, account = MERCHANTS[next(rng) % len(MERCHANTS)]
            if next(rng) % 500 == 0:
                amount = "NOTANUMBER"  # ~0.2% malformed -> rejected, not crash
            else:
                cents = next(rng) % 2_000_000  # 0 .. 20000.00
                sign = "-" if account == "bank" and next(rng) % 2 == 0 else ""
                amount = f"{sign}{cents // 100}.{cents % 100:02d}"
            dt = f"2026-{1 + next(rng) % 12:02d}-{1 + next(rng) % 28:02d}"
            if i > 0 and next(rng) % 5 == 0:  # ~20% re-sync at batch 2
                rid, batch = f"txn_{next(rng) % i}", 2
            else:
                rid, batch = f"txn_{i}", 1
            w.writerow([rid, batch, dt, account, merchant, memo, amount])


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a large transaction feed.")
    p.add_argument("rows", type=int, help="number of rows to generate")
    p.add_argument("-o", "--output", default="data/transactions_large.csv")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    generate(args.output, args.rows, args.seed)
    print(f"wrote {args.rows:,} rows to {args.output}")


if __name__ == "__main__":
    main()
