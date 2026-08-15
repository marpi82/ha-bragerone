#!/bin/bash
#
# Release script for ha-bragerone
# Usage: ./scripts/release.sh [version] [type]
#
# Process (do not skip): beta/rc pre-release → live HACS smoke → stable.
# Full checklist: DEVELOPMENT.md → "Publishing Releases".
# Tags match historical CalVer without a "v" prefix (e.g. 2026.8.5rc1).
# Tag suffix drives GitHub/HACS channel via .github/workflows/release.yml
# (tags matching (a|b|rc)[0-9]+$ are marked prerelease=true).
#
# Before tagging a pre-release/stable, bump custom_components/habragerone/manifest.json
# "version" to the same string as the tag (HACS zip embeds that file).
#
# Examples:
#   ./scripts/release.sh 2026.8.5 beta   # Pre-release first (2026.8.5b1)
#   ./scripts/release.sh 2026.8.5 rc     # Optional RC after beta (2026.8.5rc1)
#   ./scripts/release.sh 2026.8.5        # Stable only after live smoke (2026.8.5)
#   ./scripts/release.sh 2026.8.5 alpha  # Early alpha if needed

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    log_error "Not in a git repository"
    exit 1
fi

# Check if working directory is clean
if ! git diff-index --quiet HEAD --; then
    log_error "Working directory is not clean. Please commit your changes first."
    exit 1
fi

# Get version from command line
VERSION=$1
RELEASE_TYPE=${2:-stable}

if [ -z "$VERSION" ]; then
    log_error "Version is required"
    echo "Usage: $0 <version> [type]"
    echo "Types: stable (default), alpha, beta, rc"
    exit 1
fi

# Construct tag name based on release type (no "v" prefix — matches existing tags)
case $RELEASE_TYPE in
    stable)
        TAG="$VERSION"
        ;;
    alpha)
        # Find next alpha number
        ALPHA_NUM=1
        while git tag | grep -q "${VERSION}a${ALPHA_NUM}"; do
            ((ALPHA_NUM++))
        done
        TAG="${VERSION}a${ALPHA_NUM}"
        ;;
    beta)
        # Find next beta number
        BETA_NUM=1
        while git tag | grep -q "${VERSION}b${BETA_NUM}"; do
            ((BETA_NUM++))
        done
        TAG="${VERSION}b${BETA_NUM}"
        ;;
    rc)
        # Find next rc number
        RC_NUM=1
        while git tag | grep -q "${VERSION}rc${RC_NUM}"; do
            ((RC_NUM++))
        done
        TAG="${VERSION}rc${RC_NUM}"
        ;;
    *)
        log_error "Invalid release type: $RELEASE_TYPE"
        echo "Valid types: stable, alpha, beta, rc"
        exit 1
        ;;
esac

# Check if tag already exists
if git tag | grep -q "^$TAG$"; then
    log_error "Tag $TAG already exists"
    exit 1
fi

log_info "Preparing release $TAG ($RELEASE_TYPE)"

# HACS zip embeds manifest.json — version must match the tag.
MANIFEST_VERSION="$(python3 -c "import json; print(json.load(open(\"custom_components/habragerone/manifest.json\"))[\"version\"])" 2>/dev/null || true)"
if [ -z "$MANIFEST_VERSION" ]; then
    log_error "Could not read custom_components/habragerone/manifest.json version"
    exit 1
fi
if [ "$MANIFEST_VERSION" != "$TAG" ]; then
    log_error "manifest.json version ($MANIFEST_VERSION) != tag ($TAG). Bump manifest first."
    exit 1
fi

# Show what will be published
if [ "$RELEASE_TYPE" = "stable" ]; then
    log_info "This will create a stable GitHub release"
else
    log_info "This will create a GitHub pre-release"
fi

# Confirm with user
read -p "Do you want to continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Release cancelled"
    exit 0
fi

# Update to latest main branch
log_info "Updating to latest main branch..."
git checkout main
git pull origin main

# Create and push tag
log_info "Creating tag $TAG..."
git tag -a "$TAG" -m "Release $TAG"

log_info "Pushing tag $TAG..."
git push origin "$TAG"

log_info "Release $TAG has been created and pushed!"
log_info "GitHub Actions will now:"
echo "  1. Build the package"
echo "  2. Create GitHub release"
echo "  3. Attach release artifacts"

log_info "Check the progress at: https://github.com/marpi82/ha-bragerone/actions"