# Release Setup

This project is released through GitHub tags and GitHub Actions (HACS zip +
GitHub Release). It is **not** published to PyPI.

> **Note:** This file keeps the legacy name `PYPI_SETUP.md`.
> Canonical maintainer checklist: [`DEVELOPMENT.md`](../DEVELOPMENT.md) →
> “Publishing Releases”. Branch/tag rulesets:
> [`.github/branch-protection-checklist.md`](../.github/branch-protection-checklist.md).

## Configuration Overview

- **Stable releases** (tags without `a` / `b` / `rc`) → GitHub Release (HACS default)
- **Pre-releases** (`aN` / `bN` / `rcN` tags) → GitHub Pre-release (HACS beta)
- Tags use CalVer **without** a `v` prefix (for example `2026.9.0`, `2026.9.0rc1`)
- **`main`**: stable and pre-releases
- **`release/*`**: pre-releases only — merge to `main` before a stable tag

## Release Process

Prefer the helper (tags the **current** branch):

```bash
# From main or release/YYYY.M — pre-release first
./scripts/release.sh 2026.9.0 rc

# Stable — only from main, after HACS beta smoke
./scripts/release.sh 2026.9.0 stable
```

Manual tags (same naming rules):

```bash
git tag -a 2026.9.0rc1 -m "Release 2026.9.0rc1"
git push origin 2026.9.0rc1
```

Bump `custom_components/habragerone/manifest.json` `"version"` to the exact tag
string before tagging.

### What happens automatically

1. CI runs on the tag push
2. On CI success, the Release workflow builds artifacts and creates a GitHub release
3. **Enforce release channel** refuses a stable tag unless the commit is on
   `origin/main`, and refuses a pre-release unless the commit is on `main` or
   `release/*`
4. Assets (including `ha-bragerone-hacs.zip`) are attached to the release

## Versioning

- Stable: `YYYY.M.N` (e.g. `2026.9.0`)
- Pre-release: `YYYY.M.NaN`, `YYYY.M.NbN`, `YYYY.M.NrcN`

## Troubleshooting

### Release workflow did not start

- Verify the tag was pushed to `origin`
- Confirm CI completed successfully (Release is `workflow_run` after CI)

### Release exists but no assets

- Open the workflow run logs in GitHub Actions
- Verify build step completed successfully before upload steps
