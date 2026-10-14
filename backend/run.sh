#!/usr/bin/env bash
# Veritas Engine - local backend launcher (Linux / macOS)
# Usage: ./run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8000}"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
exec .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
