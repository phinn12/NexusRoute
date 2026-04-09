#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_python() {
  local required_modules=("$@")
  local candidate
  for candidate in "$ROOT_DIR/venv" "$ROOT_DIR/.venv" "$ROOT_DIR/../.venv"; do
    if [ ! -x "$candidate/bin/python" ]; then
      continue
    fi
    if "$candidate/bin/python" - "$candidate" "${required_modules[@]}" <<'PY' >/dev/null 2>&1
import importlib.util
import pathlib
import sys

expected = pathlib.Path(sys.argv[1]).resolve()
actual = pathlib.Path(sys.prefix).resolve()
if actual != expected:
    raise SystemExit(1)

for module_name in sys.argv[2:]:
    if not importlib.util.find_spec(module_name):
        raise SystemExit(1)

raise SystemExit(0)
PY
    then
      printf '%s\n' "$candidate/bin/python"
      return 0
    fi
  done

  echo "Sağlıklı bir sanal ortam bulunamadı. Beklenen adaylar: venv, .venv, ../.venv" >&2
  return 1
}

PYTHON_BIN="$(resolve_python uvicorn.main)"

HOST=${BACKEND_HOST:-0.0.0.0}
PORT=${BACKEND_PORT:-8010}

echo "Starting backend on http://${HOST}:${PORT}"
"$PYTHON_BIN" -m uvicorn kargo_backend.api:app --host "$HOST" --port "$PORT"
