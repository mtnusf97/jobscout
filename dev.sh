#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Pick a Python ≥ 3.11
PY=""
for cand in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3.13 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PY="$cand"; break
    fi
  fi
done
if [ -z "$PY" ]; then echo "error: need Python >= 3.11 (brew install python@3.13)"; exit 1; fi

if [ ! -d backend/.venv ]; then
  echo "Creating backend venv with $PY ..."
  "$PY" -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages ..."
  (cd frontend && npm install)
fi

(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
BACK=$!
(cd frontend && npm run dev) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' EXIT INT TERM

echo ""
echo "JobScout dev running:"
echo "  UI   → http://localhost:5173"
echo "  API  → http://127.0.0.1:8000/api/health"
echo ""
wait
