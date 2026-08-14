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

### Running Tests

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=custom_components.habragerone --cov-report=term-missing
```

CI uploads `coverage.xml` to Codecov (skipped for Dependabot/Renovate and fork PRs). Pull requests get a `codecov-commenter` report. Patch coverage target is 100%; overall project coverage is informational (the 80% floor is the pre-push hook — see setup commands above).

Same-repo PRs also re-request GitHub Copilot code review (`.github/workflows/copilot-rerequest.yml`, secret `COPILOT_REVIEW_TOKEN`). Issue and PR templates live under `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md`.

### Publishing Releases

The project publishes releases through GitHub Actions:

```bash
# Create stable release
./scripts/release.sh 2025.1.0

# Create pre-release
./scripts/release.sh 2025.1.0 alpha  # or beta, rc
```

Releases are automatically built and published on GitHub:
- **GitHub Releases** for stable tags (`v2025.1.0`)
- **GitHub pre-releases** for pre-release tags (`v2025.1.0a1`, `v2025.1.0b1`, `v2025.1.0rc1`)
