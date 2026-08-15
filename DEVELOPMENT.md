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

### Publishing Releases

Do **not** cut a stable HACS tag until the same version has been smoke-tested as a HACS **pre-release** on a live Home Assistant install. Tooling already supports this (`scripts/release.sh` + `.github/workflows/release.yml`); skipping the beta/rc step is a process failure, not a tooling gap.

#### Release checklist (maintainers)

1. Land the release candidates on `main` (CI green).
2. Tag a **pre-release** (prefer `beta`, then `rc` if needed):

   ```bash
   ./scripts/release.sh 2026.x.y beta   # pushes v2026.x.yb1 → GitHub pre-release
   ```

3. In HACS, enable **Show beta versions** (or equivalent) and install/update the pre-release on a **live** HA instance.
4. Smoke-test at least: config flow / reconfigure, entity count and naming, a few writes, reconnect / module connectivity.
5. Fix blockers on `main` and retag another `beta`/`rc` if needed.
6. Only then cut **stable**:

   ```bash
   ./scripts/release.sh 2026.x.y stable # pushes v2026.x.y → GitHub release (HACS default)
   ```

Tag suffix matters: `.github/workflows/release.yml` (`Detect tag and pre-release`) sets `prerelease=true` when the tag matches `(a|b|rc)[0-9]+$` (`v2026.x.ya1`, `…b1`, `…rc1`). HACS surfaces those as opt-in pre-releases; unsuffixed `v2026.x.y` is the stable channel.

#### Commands

```bash
# Pre-release (alpha / beta / rc) — always before the matching stable
./scripts/release.sh 2026.x.y beta

# Stable — only after live smoke on the pre-release
./scripts/release.sh 2026.x.y
# or explicitly:
./scripts/release.sh 2026.x.y stable
```

GitHub Actions then builds the package and publishes:
- **GitHub Releases** for stable tags (`v2026.x.y`)
- **GitHub pre-releases** for suffixed tags (`v2026.x.ya1`, `v2026.x.yb1`, `v2026.x.yrc1`)
