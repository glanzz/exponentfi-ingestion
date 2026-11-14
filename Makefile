.PHONY: install run test clean

# Install runtime + dev deps into the current environment.
install:
	pip install -e ".[dev]"

# Produce ledger_lines.csv (and rejected_rows.csv) from the sample feed.
run:
	python -m ledger data/transactions.csv -o ledger_lines.csv

test:
	python -m pytest

clean:
	rm -f ledger_lines.csv rejected_rows.csv *.checkpoint.json
	rm -rf out .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
