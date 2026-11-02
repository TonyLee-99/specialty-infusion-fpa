# specialty-infusion-fpa. `make check` is fast and offline (committed fixtures/outputs);
# `make reproduce` rebuilds everything from fresh public pulls.
SHELL := /bin/bash
PY    := PYTHONPATH=src .venv/bin/python -W ignore
DBT   := cd dbt && ../.venv/bin/dbt
export DBT_PROFILES_DIR := $(CURDIR)/dbt

.PHONY: init check lint test dbt-ci verify reproduce ingest dbt fixtures analyses margin forecast \
        scenarios excel benchmark market rcm exports kpis memo scorecard screenshots readme dq \
        monthly-pack clean

init:             ## fresh clone -> working env (venv, pinned deps, browser for screenshots)
	bash scripts/init.sh

check: lint test dbt-ci   ## lint + unit/output tests + dbt on fixtures + feature regression check
	$(PY) scripts/verify_features.py --check-only

lint:
	.venv/bin/ruff check src tests scripts

test:
	$(PY) -m pytest -q

dbt-ci:           ## dbt build (models + data tests) on the committed fixture warehouse
	$(DBT) build --target ci --quiet

verify:           ## the ONLY writer of feature_list.json state/evidence
	$(PY) scripts/verify_features.py

# ---------- full rebuild from public sources ----------
reproduce: ingest dbt fixtures analyses exports kpis excel memo scorecard screenshots readme dq test
	@echo "make reproduce: OK"

ingest:           ## filtered CMS / CDC / Census pulls -> data/raw/*.parquet + data_manifest.json
	$(PY) -m sifpa.ingest.run

dbt:              ## dbt build on the full warehouse (data/warehouse.duckdb)
	$(DBT) build --target dev --quiet

fixtures:         ## small slice of raw data for offline CI dbt runs (tests/fixtures/raw)
	$(PY) -m sifpa.fixtures

analyses: margin forecast scenarios benchmark market rcm

margin:
	$(PY) -m sifpa.margin
forecast:
	$(PY) -m sifpa.forecast
scenarios:
	$(PY) -m sifpa.scenarios
benchmark:
	$(PY) -m sifpa.benchmark
market:
	$(PY) -m sifpa.market
rcm:              ## SYNTHETIC revenue-cycle method demo
	$(PY) -m sifpa.rcm.generate
	$(PY) -m sifpa.rcm.kpis

exports:          ## star schema CSVs for the Power BI semantic model
	$(PY) -m sifpa.exports
kpis:             ## SQL twins of the DAX measures -> outputs/kpis.json
	$(PY) -m sifpa.kpis
excel:            ## scenario workbook with live formulas (+ LibreOffice recalculation check)
	$(PY) -m sifpa.excel_workbook
memo:
	$(PY) -m sifpa.memo
scorecard:
	$(PY) -m sifpa.scorecard
screenshots:
	$(PY) -m sifpa.screenshots
readme:           ## refresh generated README result blocks from outputs/*.json
	$(PY) -m sifpa.readme
dq:               ## data-quality checks; non-zero exit on a hard failure
	$(PY) -m sifpa.dq

monthly-pack:     ## the recurring job: refresh -> test -> rebuild extracts -> scorecard + memo
	$(PY) -m sifpa.monthly_pack

clean:
	rm -rf dbt/target dbt/logs logs/verify data/warehouse.duckdb
