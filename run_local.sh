#!/usr/bin/env bash
# run_local.sh — sanal ortam aktifse veya değilse çalıştırmak için yardımcı script
# Kullanım: ./run_local.sh yerelden_gelen
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INBOX_DIR=${1:-yerelden_gelen}

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

PYTHON_BIN="$(resolve_python)"
"$PYTHON_BIN" process_local_inbox.py --inbox "$INBOX_DIR"
