#!/usr/bin/env bash
# Prepare a local Home Assistant config tree for Cloud Agent / native `poe hass`.
# Idempotent. Does not start HA.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

CONFIG_DIR="${HASS_CONFIG:-config}"
mkdir -p "$CONFIG_DIR"

# Refresh from tracked template unless the operator opts out.
if [[ "${HASS_KEEP_CONFIG:-0}" != "1" && -f ".config/configuration.yaml" ]]; then
  cp .config/configuration.yaml "$CONFIG_DIR/configuration.yaml"
  echo "Synced $CONFIG_DIR/configuration.yaml from .config/configuration.yaml"
elif [[ ! -f "$CONFIG_DIR/configuration.yaml" ]]; then
  cat >"$CONFIG_DIR/configuration.yaml" <<'EOF'
# Lean Home Assistant config for integration smoke tests.
homeassistant:
http:
frontend:
config:
logger:
  default: info
  logs:
    custom_components.habragerone: debug
    pybragerone: debug
recorder:
history:
logbook:
EOF
  echo "Created $CONFIG_DIR/configuration.yaml"
fi

# HA loads custom integrations from <config>/custom_components
TARGET="$CONFIG_DIR/custom_components"
SOURCE="$PROJECT_DIR/custom_components"
if [[ -L "$TARGET" ]]; then
  ln -sfn "$SOURCE" "$TARGET"
elif [[ -e "$TARGET" ]]; then
  echo "WARNING: $TARGET exists and is not a symlink; leave it as-is."
else
  ln -s "$SOURCE" "$TARGET"
  echo "Linked $TARGET -> $SOURCE"
fi

# Optional: install sibling py-bragerone editable for unreleased library testing.
# HA startup should then use --skip-pip (see cloud_hass_start.sh) so requirements
# from manifest.json do not overwrite the editable install.
if [[ "${USE_LOCAL_PYBRAGERONE:-0}" == "1" ]]; then
  SIBLING="${PY_BRAGERONE_PATH:-$PROJECT_DIR/../py-bragerone}"
  if [[ ! -d "$SIBLING" ]]; then
    echo "ERROR: USE_LOCAL_PYBRAGERONE=1 but sibling not found at $SIBLING" >&2
    exit 1
  fi
  echo "Installing editable py-bragerone from $SIBLING"
  uv pip install -e "$SIBLING"
fi

# With --skip-pip (Cloud Agent default), HA will not fetch frontend wheels itself.
# Ensure UI packages exist in the uv venv.
if ! uv run python -c 'import hass_frontend, turbojpeg' >/dev/null 2>&1; then
  echo "Installing HA UI deps (home-assistant-frontend, PyTurboJPEG)…"
  uv pip install home-assistant-frontend PyTurboJPEG
else
  echo "HA UI deps present (hass_frontend, turbojpeg)"
fi

echo "Home Assistant config ready under $CONFIG_DIR"
echo "Next: uv run poe hass-cloud   # or ./scripts/cloud_hass_start.sh"
