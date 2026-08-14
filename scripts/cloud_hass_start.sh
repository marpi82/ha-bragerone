#!/usr/bin/env bash
# Start Home Assistant for Cloud Agent smoke tests (native, no Docker).
# Prepares config, launches HA in a tmux session, waits until :8123 answers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

CONFIG_DIR="${HASS_CONFIG:-config}"
SESSION="${HASS_TMUX_SESSION:-ha-bragerone}"
PORT="${HASS_PORT:-8123}"
SKIP_PIP="${HASS_SKIP_PIP:-1}"
TMUX_CONF="${TMUX_CONF:-/exec-daemon/tmux.portal.conf}"

"$SCRIPT_DIR/cloud_hass_prepare.sh"

TMUX=(tmux)
if [[ -f "$TMUX_CONF" ]]; then
  TMUX=(tmux -f "$TMUX_CONF")
fi

if "${TMUX[@]}" has-session -t "=$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' already exists — not starting a second HA."
else
  if [[ "$SKIP_PIP" == "1" ]]; then
    START_CMD="uv run python -m homeassistant --config '$CONFIG_DIR' --debug --skip-pip"
  else
    START_CMD="uv run python -m homeassistant --config '$CONFIG_DIR' --debug"
  fi
  "${TMUX[@]}" new-session -d -s "$SESSION" -c "$PROJECT_DIR" -- \
    "${SHELL:-bash}" -lc "$START_CMD 2>&1 | tee '$CONFIG_DIR/home-assistant.boot.log'"
  echo "Started HA in tmux session '$SESSION'"
fi

echo "Waiting for http://127.0.0.1:${PORT}/ …"
for _ in $(seq 1 90); do
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/"; then
    echo "Home Assistant is up: http://127.0.0.1:${PORT}/"
    if [[ -f "$TMUX_CONF" ]]; then
      echo "Attach logs: tmux -f $TMUX_CONF attach -t $SESSION"
    else
      echo "Attach logs: tmux attach -t $SESSION"
    fi
    echo "First visit shows onboarding unless .storage already exists."
    exit 0
  fi
  sleep 2
done

echo "ERROR: HA did not become ready on :${PORT} within timeout." >&2
echo "--- last boot log ---" >&2
tail -n 80 "$CONFIG_DIR/home-assistant.boot.log" 2>/dev/null || true
exit 1
