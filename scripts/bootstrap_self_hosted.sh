#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

STATE_ROOT="${SELF_HOSTED_STATE_DIR:-$HOME/.cache/auto-check}"
CONFIG_DIR="${SELF_HOSTED_CONFIG_DIR:-$HOME/.config/auto-check}"
ENV_FILE="${SELF_HOSTED_ENV_FILE:-$CONFIG_DIR/auto-check.env}"
VENV_DIR="${SELF_HOSTED_VENV_DIR:-$STATE_ROOT/venv}"

detect_browser() {
  local candidate
  for candidate in chromium chromium-browser google-chrome google-chrome-stable; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_python_certificates() {
  local cert_path=""

  cert_path="$(python3 - <<'PY' 2>/dev/null || true
try:
    import certifi
    print(certifi.where())
except Exception:
    pass
PY
)"

  if [[ -z "$cert_path" ]]; then
    python3 -m pip install --user --upgrade \
      --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org \
      --trusted-host pypi.python.org \
      certifi

    cert_path="$(python3 - <<'PY'
import certifi
print(certifi.where())
PY
)"
  fi

  export SSL_CERT_FILE="$cert_path"
  export PIP_CERT="$cert_path"
}

mkdir -p "$STATE_ROOT/runtime" "$STATE_ROOT/browser-profile" "$CONFIG_DIR"

ensure_python_certificates

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"

BROWSER_PATH_VALUE="${BROWSER_PATH:-}"
if [[ -z "$BROWSER_PATH_VALUE" ]]; then
  BROWSER_PATH_VALUE="$(detect_browser || true)"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<EOF
# Self-hosted runtime
RUNTIME_DIR=$STATE_ROOT/runtime
BROWSER_USER_DATA_DIR=$STATE_ROOT/browser-profile
COOKIE_SNAPSHOT_PATH=$STATE_ROOT/runtime/linuxdo-cookies.txt
LOCK_FILE=$STATE_ROOT/runtime/auto-check.lock

# Browser
BROWSER_HEADLESS=true
BROWSER_PROFILE_NAME=Default
BROWSER_PATH=${BROWSER_PATH_VALUE}
MANUAL_LOGIN_ENABLED=false

# Login
LINUXDO_COOKIES=
LINUXDO_USERNAME=
LINUXDO_PASSWORD=

# Task
BROWSE_ENABLED=true
TOPIC_COUNT=10

# Notifications
GOTIFY_URL=
GOTIFY_TOKEN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SC3_PUSH_KEY=
WXPUSH_URL=
WXPUSH_TOKEN=
EOF
fi

cat <<EOF
Bootstrap finished.

Repo dir:     $REPO_DIR
State root:   $STATE_ROOT
Config file:  $ENV_FILE
Python venv:  $VENV_DIR
Browser path: ${BROWSER_PATH_VALUE:-<not found>}

Next steps:
1. Edit $ENV_FILE and fill in your login / notification values.
2. If browser path was not detected, install Chromium/Chrome and update BROWSER_PATH.
3. Initialize session once:
   BROWSER_HEADLESS=false $REPO_DIR/scripts/run_self_hosted.sh --init-session
4. Test a normal run:
   $REPO_DIR/scripts/run_self_hosted.sh
EOF
