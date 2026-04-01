#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

STATE_ROOT="${SELF_HOSTED_STATE_DIR:-$HOME/.cache/auto-check}"
CONFIG_DIR="${SELF_HOSTED_CONFIG_DIR:-$HOME/.config/auto-check}"
ENV_FILE="${SELF_HOSTED_ENV_FILE:-$CONFIG_DIR/auto-check.env}"
VENV_DIR="${SELF_HOSTED_VENV_DIR:-$STATE_ROOT/venv}"

detect_certifi_path() {
  python3 - <<'PY' 2>/dev/null || true
try:
    import certifi
    print(certifi.where())
except Exception:
    pass
PY
}

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${SSL_CERT_FILE:-}" ]]; then
  CERT_PATH="$(detect_certifi_path)"
  if [[ -n "$CERT_PATH" ]]; then
    export SSL_CERT_FILE="$CERT_PATH"
    export PIP_CERT="$CERT_PATH"
  fi
fi

mkdir -p "${RUNTIME_DIR:-$STATE_ROOT/runtime}" "${BROWSER_USER_DATA_DIR:-$STATE_ROOT/browser-profile}"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  PYTHON_BIN="$VENV_DIR/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

cd "$REPO_DIR"
exec "$PYTHON_BIN" main.py "$@"
