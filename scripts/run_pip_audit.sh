#!/usr/bin/env bash
# Run pip-audit for the locked environment.
# HA 2026.11+ pins Pillow==13.0.0 — do not re-add Pillow 12.x ignores.
# Bump unpinned transitive/build deps (filelock, setuptools via hatch-vcs) in
# the lockfile instead of ignoring them. Only add --ignore-vuln for HA-pinned
# advisories that still fire after a bump, and keep the list equal to what
# pip-audit currently reports.
set -euo pipefail

uv run --group dev pip-audit \
  --format=json \
  --output=pip-audit-results.json \
  --progress-spinner=off \
  --skip-editable
