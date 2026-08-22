## Development

This project uses:

- Python 3.14.2+
- uv for dependency management
- pre-commit for code quality
- Docker Compose for development environment

### Setup Development Environment

```bash
# Install dependencies
uv sync --group dev --group test

# Install pre-commit hooks (commit-stage checks)
uv run pre-commit install

# Install pre-push hook (80% coverage gate on git push)
uv run pre-commit install --hook-type pre-push

# Start development environment
docker-compose up -d
```

### Cursor Cloud / native HA (no Docker)

When Docker is unavailable (Cloud Agent), use:

```bash
uv run poe hass-prepare
uv run poe hass-cloud    # http://127.0.0.1:8123
```

See `AGENTS.md` → **Cursor Cloud specific instructions**.

### Running Tests

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=custom_components.habragerone --cov-report=term-missing
```

CI uploads `coverage.xml` to Codecov (skipped for Dependabot/Renovate and fork PRs). Pull requests get a `codecov-commenter` report. Patch coverage target is 100%; overall project coverage is informational (the 80% floor is the pre-push hook — see setup commands above).

Issue and PR templates live under `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md`. Optional Copilot code review is configured in the GitHub repo settings (not via a workflow).

### Diagnostics: obfuscated `minValue` / `maxValue` strings

Some SPA factory mappings still emit unevaluated expressions in diagnostics dumps
(for example `_0x…?.['minValue']||[{group,number,use}]`). Everyday Number/Select
`min`/`max` already come from ParamStore channels `n`/`x` on the primary register,
so users usually see correct limits.

Catalog-side extraction of those `||` fallbacks is tracked and fixed in
[py-bragerone#329](https://github.com/marpi82/py-bragerone/issues/329) /
PR targeting `release/2026.9`. No Home Assistant code change is required for that
parser fix; bump the `py-bragerone` pin when a matching pre-release from that train
is published.

### Module alarms sensors (#222)

Per-module diagnostic sensors expose SPA **current** and **history** alarms (`alarm.currentAlarms` / `alarm.historyAlarms`) with state = item count and an `alarms` attribute list (`id`, `name`, `devid`, `created_at`, `finished_at`). Labels come from SPA i18n / `AlarmName` via `pybragerone` (never hardcoded PL/EN). Lists refresh on platform setup and when a module connectivity flip goes online — no blind polling. Requires a `py-bragerone` build that provides `modules_alarms` / `modules_alarms_history` (see library PR #338); older pins skip entity creation.

### Publishing Releases

Do **not** cut a stable HACS tag until the same version has been smoke-tested as a HACS **pre-release** on a live Home Assistant install. Tooling already supports this (`scripts/release.sh` + `.github/workflows/release.yml`); skipping the beta/rc step is a process failure, not a tooling gap.

**Channels:**

| Branch | Allowed tags |
|--------|----------------|
| `main` | Stable (`2026.x.y`) and pre (`aN` / `bN` / `rcN`) |
| `release/YYYY.M` or `release/YYYY.M.N` | Pre only — `release.sh` and the release workflow refuse stable |

`scripts/release.sh` tags the **current** branch (it no longer switches to `main`). The branch tip must already be on the remote. When testing a train, pin `py-bragerone==…` in `manifest.json`, keep `pyproject.toml` / `uv.lock` aligned, and bump `manifest.json` `"version"` to the tag. Ruleset checklist: `.github/branch-protection-checklist.md`.

#### Release checklist (maintainers) — from `main`

1. Land the release candidates on `main` (CI green), or merge a finished `release/*` train.
2. Tag a **pre-release** (prefer `beta`, then `rc` if needed):

   ```bash
   ./scripts/release.sh 2026.x.y beta   # pushes 2026.x.yb1 → GitHub pre-release
   ```

3. In HACS, enable **Show beta versions** (or equivalent) and install/update the pre-release on a **live** HA instance.
4. Smoke-test at least: config flow / reconfigure, entity count and naming, a few writes, reconnect / module connectivity.
5. Fix blockers on `main` and retag another `beta`/`rc` if needed.
6. Only then cut **stable**:

   ```bash
   ./scripts/release.sh 2026.x.y stable # pushes 2026.x.y → GitHub release (HACS default)
   ```

#### Release train (future work off `main`)

1. `git checkout -b release/2026.9` from `main`, develop there, then publish the branch:

   ```bash
   git push -u origin release/2026.9
   ```

2. Publish library pre on PyPI from the matching `py-bragerone` train, then bump the integration pin in `manifest.json`, `pyproject.toml`, and `uv.lock`, plus `manifest.json` `"version"`.
3. From the train branch (already pushed): `./scripts/release.sh 2026.9.0 rc` (alpha/beta/rc only).
4. HACS beta smoke as above.
5. Open a PR `release/2026.9` → `main`; after merge, cut stable from `main`.

Bump `custom_components/habragerone/manifest.json` `"version"` to the **exact** tag string before tagging (the HACS zip embeds that file).

Tag suffix matters: `.github/workflows/release.yml` (`Detect tag and pre-release`) sets `prerelease=true` when the tag matches `(a|b|rc)[0-9]+$` (`2026.x.ya1`, `…b1`, `…rc1`). **Enforce release channel** fails the job if a stable tag’s commit is not on `origin/main`, or if a pre-release commit is not on `origin/main` / `origin/release/*`. HACS surfaces pre tags as opt-in; unsuffixed `2026.x.y` is the stable channel. Tags do **not** use a `v` prefix (match existing releases such as `2026.8.4`).

#### Commands

```bash
# Pre-release (alpha / beta / rc) — always before the matching stable
./scripts/release.sh 2026.x.y beta

# Stable — only after live smoke; only from main (not release/*)
./scripts/release.sh 2026.x.y
# or explicitly:
./scripts/release.sh 2026.x.y stable
```

GitHub Actions then builds the package and publishes:
- **GitHub Releases** for stable tags (`2026.x.y`)
- **GitHub pre-releases** for suffixed tags (`2026.x.ya1`, `2026.x.yb1`, `2026.x.yrc1`)
