# Release Setup

This project is released through GitHub tags and GitHub Actions.
It is **not** published to PyPI/TestPyPI.

## Configuration Overview

- **Stable releases** (tags without `a`, `b`, `rc`) -> GitHub Release
- **Pre-releases** (alpha, beta, rc tags) -> GitHub Pre-release
- Release assets are attached to the GitHub release page

## Release Process

### Creating releases

You can create tags manually:

```bash
# Stable release
git tag v2025.1.0
git push origin v2025.1.0

# Pre-release
git tag v2025.1.0a1   # alpha
git push origin v2025.1.0a1
```

Or use the helper script:

```bash
./scripts/release.sh 2025.1.0
./scripts/release.sh 2025.1.0 alpha
```

### What happens automatically

1. GitHub Actions starts on tag push
2. Build artifacts are generated
3. GitHub release or pre-release is created
4. Artifacts are uploaded to the release page

## Versioning

The project uses CalVer-style tags:

- Stable: `vYYYY.M.MICRO` (e.g. `v2025.1.0`)
- Pre-release: `vYYYY.M.MICROaN`, `vYYYY.M.MICRObN`, `vYYYY.M.MICROrcN`

## Troubleshooting

### Release workflow did not start

- Verify the tag was pushed to `origin`
- Check GitHub Actions permissions and workflow triggers

### Release exists but no assets

- Open the workflow run logs in GitHub Actions
- Verify build step completed successfully before upload steps