#!/bin/bash
# Development setup script for ha-bragerone
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🏠 Setting up ha-bragerone development environment..."

# Check if we're in the right directory
if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
    echo "❌ Error: Not in ha-bragerone project directory"
    exit 1
fi

cd "$PROJECT_DIR"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Check if py-bragerone is available
if [[ -d "../py-bragerone" ]]; then
    echo "📦 Adding py-bragerone as editable dependency..."
    uv add ../py-bragerone --editable
else
    echo "⚠️  Warning: py-bragerone not found at ../py-bragerone"
    echo "   You may need to clone it or adjust the path later"
fi

# Sync dependencies
echo "📦 Syncing dependencies..."
uv sync --group dev --group test

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
uv run --group dev pre-commit install

# Setup Home Assistant config
echo "🏠 Setting up Home Assistant configuration..."
mkdir -p config

if [[ ! -f "config/configuration.yaml" ]]; then
    if [[ -f ".config/configuration.yaml" ]]; then
        cp .config/configuration.yaml config/configuration.yaml
    else
        cat > config/configuration.yaml << 'EOF'
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

# Your integration configuration
habragerone:
  # Add your configuration here
EOF
    fi
    echo "✅ Created config/configuration.yaml"
fi

# Create .env file if it doesn't exist
if [[ ! -f ".env" ]]; then
    cat > .env << 'EOF'
# Home Assistant configuration
HASS_CONFIG=./config
HASS_LOG_LEVEL=info

# Python debugger port
DEBUGPY_PORT=5678
EOF
    echo "✅ Created .env file"
fi

# Run initial validation
echo "🔍 Running initial validation..."
echo "  - Linting with ruff..."
uv run --group dev ruff check . || echo "⚠️  Some linting issues found (can be fixed with: uv run ruff check --fix .)"

echo "  - Type checking with mypy..."
uv run --group dev mypy || echo "⚠️  Some type issues found"

echo "  - Testing..."
uv run --group test pytest -q || echo "⚠️  Some tests failed"

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Start Home Assistant: uv run poe hass"
echo "   2. Open http://localhost:8123"
echo "   3. Run tests: uv run --group test pytest"
echo "   4. Lint code: uv run --group dev ruff check --fix ."
echo "   5. Full validation: uv run --group dev poe validate"
echo ""
echo "🐳 Docker alternatives:"
echo "   - Devcontainer: Open in VS Code and use 'Reopen in Container'"
echo "   - Docker Compose: docker-compose --profile devhass up -d"
echo ""
echo "🚀 Happy coding!"