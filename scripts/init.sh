#!/usr/bin/env bash
# Fresh-clone setup in one command: pinned Python env + Chromium for screenshots.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo "install uv: https://docs.astral.sh/uv/"; exit 1; }
uv venv --python 3.12 .venv
uv sync --frozen
.venv/bin/playwright install chromium || echo "playwright browser install skipped (screenshots need it)"
echo "init OK. Next: make check   (offline)   |   make reproduce   (pulls public data, ~10 min)"
