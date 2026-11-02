"""One place for repo paths so modules never hard-code them."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
WAREHOUSE = DATA / "warehouse.duckdb"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "raw"
OUTPUTS = ROOT / "outputs"
EXPORTS = ROOT / "exports"
CONFIG = ROOT / "config"
SEEDS = ROOT / "dbt" / "seeds"
DOCS = ROOT / "docs"
IMG = DOCS / "img"
SYNTHETIC = ROOT / "synthetic"
MANIFEST = ROOT / "data_manifest.json"

for _p in (RAW, OUTPUTS, EXPORTS, IMG):
    _p.mkdir(parents=True, exist_ok=True)
