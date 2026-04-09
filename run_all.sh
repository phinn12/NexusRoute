#!/usr/bin/env bash
# run_all.sh — tek komutla: inbox'u işle, sonra Streamlit UI'yi başlat
# Kullanım: ./run_all.sh [inbox_dir] [streamlit_port]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INBOX_DIR=${1:-yerelden_gelen}
PORT=${2:-8501}
API_PORT=${BACKEND_PORT:-8010}

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

PYTHON_BIN="$(resolve_python uvicorn.main streamlit.web.cli)"

# 1) inbox'u işle
echo "[1/2] Inbox işleniyor: ${INBOX_DIR}"
"$PYTHON_BIN" process_local_inbox.py --inbox "${INBOX_DIR}"
RC=$?
if [ $RC -ne 0 ]; then
  echo "process_local_inbox.py hata ile sonlandı (kod=$RC). Devam etmiyorum."
  exit $RC
fi

echo "[2/2] Backend ve Streamlit başlatılıyor"
if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  "$PYTHON_BIN" -m uvicorn kargo_backend.api:app --host 0.0.0.0 --port "${API_PORT}" >/tmp/kargo_backend.log 2>&1 &
  BACKEND_PID=$!
  trap 'kill ${BACKEND_PID} 2>/dev/null || true' EXIT
  sleep 2
fi

"$PYTHON_BIN" -m streamlit run web_normalize.py --server.headless true --server.port "${PORT}"
