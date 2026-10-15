#!/usr/bin/env bash
# Veritas Engine - local backend launcher (Linux / macOS)
# Usage: ./run.sh [port] [--full|--whisper]
set -euo pipefail
cd "$(dirname "$0")"
PORT=8000
REQUIREMENTS=requirements.txt
for arg in "$@"; do
  case "$arg" in
    --full) REQUIREMENTS=requirements-media.txt ;;
    --whisper) REQUIREMENTS=requirements-whisper.txt ;;
    *) PORT="$arg" ;;
  esac
done
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r "$REQUIREMENTS"
[ -f .env ] || cp .env.example .env
exec .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
