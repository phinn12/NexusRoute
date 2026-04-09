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

PYTHON_BIN="$(resolve_python streamlit.web.cli)"

PORT=${1:-8501}
echo "Starting Streamlit on http://localhost:$PORT"
"$PYTHON_BIN" -m streamlit run web_normalize.py --server.port "$PORT" --server.address 0.0.0.0
