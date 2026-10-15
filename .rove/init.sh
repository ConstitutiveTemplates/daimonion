#!/bin/sh
# One-time install for a fresh daimonion worktree (see worker contract).
# Usage: sh .rove/init.sh   (run from the repo root)
set -eu
cd "$(dirname "$0")/.."
uv sync
echo "OK: dependencies installed. Run tests with: .venv/bin/python -m pytest -q"
