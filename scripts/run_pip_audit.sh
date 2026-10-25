#!/usr/bin/env bash
# Run pip-audit with ignores for Home Assistant–pinned transitive advisories.
# HA 2026.10.x still pins Pillow==12.3.0, uv==0.12.23, setuptools==84.0.0
# (and older PyJWT). Bump unpinned transitive deps (e.g. filelock) in the
# lockfile instead of ignoring them.
set -euo pipefail

uv run --group dev pip-audit \
  --format=json \
  --output=pip-audit-results.json \
  --progress-spinner=off \
  --skip-editable \
  --ignore-vuln PYSEC-2026-4140 \
  --ignore-vuln PYSEC-2026-4141 \
  --ignore-vuln PYSEC-2026-4142 \
  --ignore-vuln PYSEC-2026-4143 \
  --ignore-vuln PYSEC-2026-4144 \
  --ignore-vuln PYSEC-2026-4145 \
  --ignore-vuln PYSEC-2026-4146 \
  --ignore-vuln PYSEC-2026-4147 \
  --ignore-vuln PYSEC-2026-4148 \
  --ignore-vuln PYSEC-2026-4149 \
  --ignore-vuln PYSEC-2026-4150 \
  --ignore-vuln PYSEC-2026-4151 \
  --ignore-vuln PYSEC-2026-4152 \
  --ignore-vuln PYSEC-2026-4183 \
  --ignore-vuln PYSEC-2026-4321 \
  --ignore-vuln CVE-2026-112390 \
  --ignore-vuln CVE-2026-112391 \
  --ignore-vuln CVE-2026-112392 \
  --ignore-vuln CVE-2026-112393 \
  --ignore-vuln CVE-2026-112395 \
  --ignore-vuln CVE-2026-112396 \
  --ignore-vuln CVE-2026-112397 \
  --ignore-vuln CVE-2026-112398 \
  --ignore-vuln CVE-2026-112399 \
  --ignore-vuln CVE-2026-112400 \
  --ignore-vuln CVE-2026-112401 \
  --ignore-vuln CVE-2026-112402 \
  --ignore-vuln CVE-2026-112404 \
  --ignore-vuln CVE-2026-112405 \
  --ignore-vuln CVE-2026-112406 \
  --ignore-vuln CVE-2026-112891 \
  --ignore-vuln CVE-2026-112892 \
  --ignore-vuln CVE-2026-112893 \
  --ignore-vuln CVE-2026-112894 \
  --ignore-vuln CVE-2026-112895 \
  --ignore-vuln CVE-2026-112896 \
  --ignore-vuln CVE-2026-112897 \
  --ignore-vuln CVE-2026-112899 \
  --ignore-vuln CVE-2026-112900 \
  --ignore-vuln CVE-2026-112901 \
  --ignore-vuln CVE-2026-96636 \
  --ignore-vuln CVE-2026-96637 \
  --ignore-vuln CVE-2026-96638 \
  --ignore-vuln CVE-2026-96639 \
  --ignore-vuln CVE-2026-96640 \
  --ignore-vuln CVE-2026-96641 \
  --ignore-vuln CVE-2026-96642 \
  --ignore-vuln CVE-2026-96643 \
  --ignore-vuln CVE-2026-96644 \
  --ignore-vuln CVE-2026-96778 \
  --ignore-vuln CVE-2026-114501 \
  --ignore-vuln GHSA-78g4-xqwv-q3g8 \
  --ignore-vuln GHSA-xmj3-9gf7-h52w
