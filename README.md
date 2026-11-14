# Ledger — EXP-412 Story 1

Takes a restaurant operator's raw transaction feed and produces categorized
ledger lines. Rules-based; the LLM step comes later and has a single seam
reserved for it (`ledger/stages/categorize.py`).

## How to run

```bash
# one-time: install (runtime dep is just rich; pytest is dev-only)
make install            # or: pip install -e ".[dev]"

# produce ledger_lines.csv + rejected_rows.csv from the sample feed
make run                # or: python -m ledger data/transactions.csv -o ledger_lines.csv

# tests
make test               # or: python -m pytest
```

Full CLI:

```
python -m ledger INPUT.csv -o OUTPUT.csv [--rejects PATH] [--resume] [-v]
```

Exit codes: `0` clean, `1` completed but some rows were rejected (see
`rejected_rows.csv`), `2` fatal (missing file / missing columns). Rejecting rows
is deliberate and loud — we never silently drop a money row.

## What it produces

- **`ledger_lines.csv`** — `transaction_id, date, type, category, amount,
  needs_review`. Sorted by `(date, id)`, amounts to exactly two decimals, the
  feed's sign preserved.
- **`rejected_rows.csv`** — always written (empty on a clean run): the original
  row plus `reason` and `detail`.

## How it works (short version)

`read → parse → dedupe (highest sync_batch) → classify → sort → atomic write.`
Everything streams as a generator; the only stateful stage is dedupe. Money is
`Decimal`, never float. Output is written to a temp file and atomically replaced,
and each line is keyed by `transaction_id`, so **running twice or resuming after a
crash yields a byte-identical file** and never double-counts. Parse and classify
fan out to a process pool above a row threshold (off for small feeds); dedupe and
the final sort stay serial, so the result never depends on worker scheduling.

See `initial_architecture.md` for the full design and `TECHNICAL_DESIGN.md` for
the metrics, data model, and diagrams.

## What I found unclear or wrong, and would ask before merging

- **"Memo says PAYMENT or TRANSFER → transfer" is wrong as stated.** `txn_1022`
  is MAINLINE PROPERTIES (Rent) with memo `ACH PAYMENT MAINLINE PROPERTIES`. The
  naive rule would book $6,500 of rent as a non-expense transfer. I made a
  memo-and-merchant agreement check: when a transfer-keyword memo lands on a
  merchant that's on the expense list, it's a **conflict** → `Uncategorized,
  needs_review=true` rather than a silent wrong answer. *Would ask:* is review the
  desired behavior, or should it force the merchant's category?
- **Are sync batches deltas or full snapshots?** I assumed deltas — batch 2 has
  only 12 rows, clearly not a replacement for batch 1's 48. So a vanished id is
  **kept**, not treated as cancelled. If batches are full snapshots, absence
  would mean "cancelled" and this flips.
- **Sign convention.** The feed uses positive = money out on *both* accounts
  (unusual for a bank). Verified against the data; I'd confirm with the provider
  and I assert it at parse time.
- **Positive payout (clawback) and unpaired transfer legs** don't appear in the
  sample. I flag a positive payout for review; I'd confirm that's wanted.
- **Same-id duplicate within one batch** doesn't occur in the sample. I keep the
  last row in file order and log the loser to rejects. Would confirm the
  tie-break.

## Where I used AI and where I overrode it

- **AI drafted** the module scaffolding, the error/rejection plumbing, the Rich
  logging, and most test bodies.
- **I overrode AI** on the transfer rule — the model's first instinct was to
  follow the spec literally (memo-only), which misclassifies MAINLINE; I checked
  it against the real feed, caught the bug, and changed it to the
  agreement-check-then-review behavior. I also replaced a byte-offset resume
  (which breaks because `csv.reader` disables `f.tell()`, caught by actually
  running it) with a re-read-from-top resume that leans on idempotent output.
- **Verification is mine, not the model's claims:** the first 15 output rows are
  diffed byte-for-byte against `expected_first_15.csv`, and parallel/serial and
  resume runs are checked to be byte-identical.
```
