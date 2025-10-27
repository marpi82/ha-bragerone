#!/bin/bash
# Devcontainer setup script for ha-bragerone
set -euo pipefail

echo "🚀 Setting up ha-bragerone devcontainer..."

# Install system dependencies (with sudo if running as non-root)
echo "📦 Installing system dependencies..."
if [ "$EUID" -ne 0 ]; then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        ca-certificates \
        libjpeg-dev \
        zlib1g-dev \
        libtiff5-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libwebp-dev \
        tcl8.6-dev \
        tk8.6-dev \
        python3-tk \
        libssl-dev \
        libffi-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncurses5-dev \
        libncursesw5-dev \
        xz-utils \
        llvm \
        libxml2-dev \
        libxmlsec1-dev
else
    apt-get update
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        ca-certificates \
        libjpeg-dev \
        zlib1g-dev \
        libtiff5-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libwebp-dev \
        tcl8.6-dev \
        tk8.6-dev \
        python3-tk \
        libssl-dev \
        libffi-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncurses5-dev \
        libncursesw5-dev \
        xz-utils \
        llvm \
        libxml2-dev \
        libxmlsec1-dev \
        gh
fi

# Install uv for current user
echo "📦 Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Fix permissions for mounted volumes (they may be owned by root)
echo "🔧 Fixing volume permissions..."
if [ -d "$HOME/.cache" ]; then
    sudo chown -R vscode:vscode "$HOME/.cache" 2>/dev/null || true
fi
if [ -d "${VIRTUAL_ENV:-$PWD/.venv}" ]; then
    sudo chown -R vscode:vscode "${VIRTUAL_ENV:-$PWD/.venv}" 2>/dev/null || true
fi
if [ -d "$PWD/config" ]; then
    sudo chown -R vscode:vscode "$PWD/config" 2>/dev/null || true
fi

# Add py-bragerone as editable dependency
echo "📦 Adding py-bragerone as editable dependency..."
if [ -d "../py-bragerone" ]; then
    uv add ../py-bragerone --editable
else
    echo "⚠️  Warning: py-bragerone not found at ../py-bragerone"
    echo "   You may need to add it manually later with: uv add /path/to/py-bragerone --editable"
fi

# Sync dependencies
echo "📦 Syncing project dependencies..."
uv sync --group dev --group test --group docs

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
uv run --group dev pre-commit install

# Setup Home Assistant config if not exists
echo "🏠 Setting up Home Assistant configuration..."
if [ ! -f "config/configuration.yaml" ]; then
    mkdir -p config
    cp .config/configuration.yaml config/configuration.yaml 2>/dev/null || {
        cat > config/configuration.yaml << EOF
# Home Assistant development configuration
default_config:

# Enable frontend
frontend:

# Logger configuration
logger:
  default: info
  logs:
    custom_components.habragerone: debug

# Development configuration
# Uncomment for demo data
# demo:
EOF
    }
fi

# Add uv to shell profile if not already there
echo "🔧 Configuring shell environment..."
if ! grep -q '.local/bin' "$HOME/.zshrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
fi

echo "✅ Devcontainer setup complete!"
echo ""
echo "Available commands:"
echo "  uv run --group test pytest                    # Run tests"
echo "  uv run --group dev ruff check .               # Lint code"
echo "  uv run --group dev mypy                       # Type check"
echo "  uv run --group dev poe <task>                 # Run poe task"
echo "  uv run --group dev poe validate               # Full validation"
echo "  uv run poe hass                               # Start Home Assistant"
echo "  uv run poe hass-restart                       # Restart Home Assistant"
echo ""
echo "🏠 Home Assistant will be available at:"
echo "   http://localhost:8123"
echo ""
echo "🐛 Python debugger available on port 5678"
