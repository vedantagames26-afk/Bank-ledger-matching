#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --cache-dir /workspace/.pip-cache -r backend/requirements.txt
npm ci --prefix frontend --cache /workspace/.npm-cache --no-audit --no-fund
npm run build --prefix frontend
