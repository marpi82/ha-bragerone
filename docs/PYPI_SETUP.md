# PyPI Publishing Setup

This project is configured to automatically publish to PyPI using GitHub Actions with Trusted Publisher (OpenID Connect) authentication.

## Configuration Overview

- **Stable releases** (tags without `a`, `b`, `rc`) → PyPI
- **Pre-releases** (alpha, beta, rc) → TestPyPI
- Uses **Trusted Publisher** (no API tokens needed)

## PyPI Trusted Publisher Setup

### 1. PyPI (for stable releases)

1. Go to [PyPI](https://pypi.org/) and log in
2. Navigate to "Publishing" → "Add a new pending publisher"
3. Fill in the form:
   - **PyPI project name**: `ha-bragerone` (or your chosen package name)
   - **Owner**: `marpi82` (your GitHub username)
   - **Repository name**: `ha-bragerone`
   - **Workflow filename**: `release.yml`
   - **Environment name**: leave empty (not using environments)

### 2. TestPyPI (for pre-releases)

1. Go to [TestPyPI](https://test.pypi.org/) and log in
2. Navigate to "Publishing" → "Add a new pending publisher"
3. Fill in the same information as above

## Package Name Configuration

The package name is defined in `pyproject.toml`:

```toml
[project]
name = "ha-bragerone"
```

Make sure this matches the name you registered on PyPI.

## Release Process

### Creating Releases

1. **For stable release**:
   ```bash
   git tag v2025.1.0
   git push origin v2025.1.0
   ```

2. **For pre-release**:
   ```bash
   git tag v2025.1.0a1    # alpha
   git tag v2025.1.0b1    # beta
   git tag v2025.1.0rc1   # release candidate
   git push origin v2025.1.0a1
   ```

### What Happens Automatically

1. **GitHub Actions runs** when you push a tag
2. **Builds the package** using `hatch build`
3. **Creates GitHub Release** with:
   - HACS-compatible ZIP file
   - Python wheel and source distribution
   - Auto-generated changelog
4. **Publishes to PyPI**:
   - Pre-releases → TestPyPI
   - Stable releases → PyPI
   - Uses Trusted Publisher (no tokens needed)

## Versioning

The project uses **CalVer** (Calendar Versioning) with `hatch-vcs`:

- **Format**: `YYYY.M.MICRO` (e.g., `2025.1.0`)
- **Pre-releases**: `2025.1.0a1`, `2025.1.0b1`, `2025.1.0rc1`
- **Automatic versioning** from git tags

## Testing Installation

### From TestPyPI (pre-releases)
```bash
pip install --index-url https://test.pypi.org/simple/ ha-bragerone
```

### From PyPI (stable releases)
```bash
pip install ha-bragerone
```

## Troubleshooting

### Common Issues

1. **"Project does not exist"** on first release
   - Create the project manually on PyPI first, or
   - Use the "pending publisher" feature before first release

2. **Permission denied**
   - Verify Trusted Publisher configuration
   - Check that `id-token: write` permission is set in workflow

3. **Package name conflicts**
   - Choose a unique package name
   - Update `pyproject.toml` accordingly

### Manual Publishing (if needed)

If automatic publishing fails, you can publish manually:

```bash
# Install dependencies
uv sync --group dev

# Build package
uv run --group dev hatch build

# Publish to TestPyPI
uv run --group dev hatch publish --repo test

# Publish to PyPI
uv run --group dev hatch publish
```

Note: Manual publishing requires API tokens configured in `~/.pypirc` or environment variables.