#!/usr/bin/env bash
# Run pip-audit with ignores for Home Assistant–pinned transitive advisories.
# HA still pins Pillow==12.3.0 (fixed in 13.0.0). Keep this list equal to the
# IDs pip-audit currently reports for that pin — drop stale entries when HA bumps.
# Bump unpinned transitive/build deps (filelock, setuptools via hatch-vcs) in
# the lockfile instead of ignoring them.
set -euo pipefail

uv run --group dev pip-audit \
  --format=json \
  --output=pip-audit-results.json \
  --progress-spinner=off \
  --skip-editable \
  --ignore-vuln CVE-2026-112390 \
  --ignore-vuln CVE-2026-112391 \
  --ignore-vuln CVE-2026-112393 \
  --ignore-vuln CVE-2026-112395 \
  --ignore-vuln CVE-2026-112399 \
  --ignore-vuln CVE-2026-112400 \
  --ignore-vuln CVE-2026-112401 \
  --ignore-vuln CVE-2026-112404 \
  --ignore-vuln CVE-2026-112406 \
  --ignore-vuln CVE-2026-112891 \
  --ignore-vuln CVE-2026-112892 \
  --ignore-vuln CVE-2026-112893 \
  --ignore-vuln CVE-2026-112894 \
  --ignore-vuln CVE-2026-112895 \
  --ignore-vuln CVE-2026-112897 \
  --ignore-vuln CVE-2026-112899 \
  --ignore-vuln CVE-2026-112900 \
  --ignore-vuln CVE-2026-128066 \
  --ignore-vuln CVE-2026-128067 \
  --ignore-vuln CVE-2026-96638 \
  --ignore-vuln CVE-2026-96640 \
  --ignore-vuln CVE-2026-96778 \
  --ignore-vuln GHSA-78g4-xqwv-q3g8 \
  --ignore-vuln PYSEC-2026-4326 \
  --ignore-vuln PYSEC-2026-4327 \
  --ignore-vuln PYSEC-2026-4328 \
  --ignore-vuln PYSEC-2026-4329 \
  --ignore-vuln PYSEC-2026-4330 \
  --ignore-vuln PYSEC-2026-4331 \
  --ignore-vuln PYSEC-2026-4332 \
  --ignore-vuln PYSEC-2026-4333 \
  --ignore-vuln PYSEC-2026-4334 \
  --ignore-vuln PYSEC-2026-4335 \
  --ignore-vuln PYSEC-2026-4336 \
  --ignore-vuln PYSEC-2026-4337 \
  --ignore-vuln PYSEC-2026-4338 \
  --ignore-vuln PYSEC-2026-4339 \
  --ignore-vuln PYSEC-2026-4340 \
  --ignore-vuln PYSEC-2026-4341 \
  --ignore-vuln PYSEC-2026-4342 \
  --ignore-vuln PYSEC-2026-4343 \
  --ignore-vuln PYSEC-2026-4363
