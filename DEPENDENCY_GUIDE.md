# py-bragerone Dependency Guide

## Current Situation

The `py-bragerone` library is required by this Home Assistant integration but is currently only published to TestPyPI, not the public PyPI. This causes installation failures in production environments and CI/CD pipelines.

## Problem

Home Assistant installs custom component dependencies from PyPI by default. When a user installs this integration:
1. Home Assistant reads `manifest.json` and sees `py-bragerone>=2025.0.0` in requirements
2. It attempts to install from PyPI (not TestPyPI)
3. Installation fails because the package doesn't exist on PyPI

## Solutions

### Option 1: Publish to PyPI (Recommended for Production)

**Pros:**
- Works out-of-the-box for all users
- Standard Home Assistant practice
- No special configuration needed

**Steps:**
1. Go to [https://pypi.org/](https://pypi.org/) and create an account (if you don't have one)
2. Set up PyPI publishing in the py-bragerone repository:
   ```bash
   # In py-bragerone repository
   # Configure trusted publisher or use API token
   ```
3. Publish the package:
   ```bash
   # Build and upload
   python -m build
   twine upload dist/*
   ```
4. Verify the package is available at `https://pypi.org/project/py-bragerone/`

### Option 2: Configure CI to Use TestPyPI (Testing Only)

This is a temporary solution for CI/CD while you're developing. **Do not use this for production releases.**

**Pros:**
- Quick workaround for CI
- Allows testing before PyPI publication

**Cons:**
- Won't work for end users
- Requires special configuration in every workflow
- Not supported by Home Assistant in production

**Implementation:**
Modify CI workflows to install from TestPyPI:
```yaml
- name: Install from TestPyPI
  run: |
    uv pip install --index-url https://test.pypi.org/simple/ \
      --extra-index-url https://pypi.org/simple/ \
      py-bragerone>=2025.0.0
```

### Option 3: Use Git URL (Development Only)

For development and testing, you can reference the GitHub repository directly:

**In manifest.json:**
```json
{
  "requirements": [
    "py-bragerone @ git+https://github.com/marpi82/py-bragerone.git@main"
  ]
}
```

**Cons:**
- Not accepted by HACS
- Slower installation
- Requires git to be available
- Not recommended for production

## Recommendation

**For this project, you should publish `py-bragerone` to PyPI.**

This is the only solution that works for end users installing your integration through HACS or manually. TestPyPI is meant for testing package uploads, not for production dependencies.

### Steps to Publish

1. **Verify your package is ready:**
   - Check version in `py-bragerone/pyproject.toml` or `setup.py`
   - Ensure README, LICENSE, and other metadata are correct
   - Test the package locally

2. **Set up PyPI authentication:**
   - Create account on PyPI.org
   - Set up API token or configure Trusted Publisher in GitHub Actions
   - Store token as GitHub secret `PYPI_TOKEN`

3. **Publish from CI or locally:**
   ```bash
   # Build the package
   python -m build
   
   # Upload to PyPI (you'll be prompted for credentials)
   twine upload dist/*
   ```

4. **Update this integration:**
   - Keep `manifest.json` requirements as is: `"py-bragerone>=2025.0.0"`
   - The package will now be installable from PyPI

## Temporary Workaround for CI

Until you publish to PyPI, we've configured the CI workflows to use TestPyPI as a fallback. This allows tests to run, but remember:
- This does NOT make your integration work for end users
- You MUST publish to PyPI before releasing to HACS or asking users to install

## Questions?

If you need help publishing to PyPI, see:
- [Python Packaging Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [Trusted Publishers for GitHub Actions](https://docs.pypi.org/trusted-publishers/)
