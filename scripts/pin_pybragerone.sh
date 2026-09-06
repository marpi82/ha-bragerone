#!/usr/bin/env bash
#
# Bump the exact py-bragerone pin in manifest.json + pyproject.toml.
# Usage: ./scripts/pin_pybragerone.sh <version>
#
# Example:
#   ./scripts/pin_pybragerone.sh 2026.9.2rc2
#   uv lock
#
# Does NOT bump the integration "version" field (use release.sh for that).
# Does NOT rewrite uv.lock — run `uv lock` after this script.
# HassOS / HACS: only pin published PyPI versions (never git+…@sha).

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
  log_error "Version is required"
  echo "Usage: $0 <py-bragerone-version>"
  echo "Example: $0 2026.9.2rc2"
  exit 1
fi

# Three-segment CalVer + optional pre-release suffix (matches library tags / PyPI).
if [[ ! "${VERSION}" =~ ^[0-9]{4}\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?$ ]]; then
  log_error "Unexpected version shape: ${VERSION}"
  echo "Expected CalVer like 2026.9.2 or 2026.9.2rc2"
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
MANIFEST="${REPO_ROOT}/custom_components/habragerone/manifest.json"
PYPROJECT="${REPO_ROOT}/pyproject.toml"

if [[ ! -f "${MANIFEST}" || ! -f "${PYPROJECT}" ]]; then
  log_error "manifest.json or pyproject.toml not found under ${REPO_ROOT}"
  exit 1
fi

python3 - "${MANIFEST}" "${VERSION}" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
version = sys.argv[2]
data = json.loads(manifest_path.read_text(encoding="utf-8"))
reqs = data.get("requirements")
if not isinstance(reqs, list):
    raise SystemExit("manifest.json requirements must be a list")
pin = f"py-bragerone=={version}"
updated: list[object] = []
found = False
for item in reqs:
    if isinstance(item, str) and (item.startswith("py-bragerone==") or item.startswith("py-bragerone@")):
        updated.append(pin)
        found = True
    else:
        updated.append(item)
if not found:
    updated.insert(0, pin)
data["requirements"] = updated
manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(pin)
PY

python3 - "${PYPROJECT}" "${VERSION}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
text = path.read_text(encoding="utf-8")
pattern = re.compile(r'(["\'])py-bragerone==[^"\']+\1')
matches = pattern.findall(text)
if len(matches) != 1:
    raise SystemExit(f"expected exactly one py-bragerone== pin in pyproject.toml, found {len(matches)}")
replacement = f'\\1py-bragerone=={version}\\1'
new_text, count = pattern.subn(replacement, text)
if count != 1:
    raise SystemExit(f"failed to rewrite py-bragerone pin (replacements={count})")
path.write_text(new_text, encoding="utf-8")
PY

log_info "Pinned py-bragerone==${VERSION} in manifest.json and pyproject.toml"
log_info "Next: uv lock && commit, then tag/release the integration when ready"
log_info "HassOS: install via HACS beta — do not use git+ pins on HassOS"
