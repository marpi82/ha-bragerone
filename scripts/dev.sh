#!/bin/bash
# Development workflow scripts for ha-bragerone
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Function to show usage
show_usage() {
    cat << 'EOF'
🏠 ha-bragerone development helper

Usage: ./scripts/dev.sh <command>

Commands:
  setup         - Initial development setup
  test          - Run tests
  test-cov      - Run tests with coverage
  lint          - Lint code with ruff
  format        - Format code with ruff
  typecheck     - Type check with mypy
  validate      - Run full validation (lint + type + test)
  pre-commit    - Run pre-commit hooks
  
  hass          - Start Home Assistant (development mode)
  hass-debug    - Start Home Assistant with debugger
  hass-demo     - Start Home Assistant with demo mode
  
  docker-dev    - Build and run development Docker container
  docker-hass   - Run Home Assistant in Docker
  docker-clean  - Clean Docker containers and volumes
  
  build         - Build the package
  clean         - Clean build artifacts and cache files
  
  help          - Show this help message

Examples:
  ./scripts/dev.sh setup        # Initial setup
  ./scripts/dev.sh validate     # Full validation before commit
  ./scripts/dev.sh hass         # Start Home Assistant
  ./scripts/dev.sh test-cov     # Tests with coverage
EOF
}

# Command implementations
cmd_setup() {
    echo "🏠 Running development setup..."
    ./scripts/setup.sh
}

cmd_test() {
    echo "🧪 Running tests..."
    uv run --group test pytest -v
}

cmd_test_cov() {
    echo "🧪 Running tests with coverage..."
    uv run --group test pytest --cov=custom_components.habragerone --cov-report=term-missing --cov-report=html
    echo "📊 Coverage report available in htmlcov/index.html"
}

cmd_lint() {
    echo "🔍 Linting code..."
    uv run --group dev ruff check --fix .
}

cmd_format() {
    echo "✨ Formatting code..."
    uv run --group dev ruff format .
}

cmd_typecheck() {
    echo "🔍 Type checking..."
    uv run --group dev mypy
}

cmd_validate() {
    echo "🔍 Running full validation..."
    echo "  1/4 Formatting..."
    uv run --group dev ruff format .
    
    echo "  2/4 Linting..."
    uv run --group dev ruff check --fix .
    
    echo "  3/4 Type checking..."
    uv run --group dev mypy
    
    echo "  4/4 Testing..."
    uv run --group test pytest -q
    
    echo "✅ All validations passed!"
}

cmd_pre_commit() {
    echo "🪝 Running pre-commit hooks..."
    uv run --group dev pre-commit run --all-files
}

cmd_hass() {
    echo "🏠 Starting Home Assistant (development mode)..."
    echo "   → http://localhost:8123"
    uv run python -m homeassistant --config ./config --log-level info
}

cmd_hass_debug() {
    echo "🏠 Starting Home Assistant with debugger..."
    echo "   → Home Assistant: http://localhost:8123"
    echo "   → Debugger: localhost:5678"
    uv run python -m debugpy --listen localhost:5678 --wait-for-client -m homeassistant -- --config ./config --log-level debug
}

cmd_hass_demo() {
    echo "🏠 Starting Home Assistant (demo mode)..."
    echo "   → http://localhost:8123"
    uv run python -m homeassistant --config ./config --demo-mode --log-level info
}

cmd_docker_dev() {
    echo "🐳 Building and running development Docker container..."
    docker build -f Dockerfile.dev -t ha-bragerone-dev .
    docker run -it --rm -v "$(pwd):/workspace" -p 5678:5678 ha-bragerone-dev
}

cmd_docker_hass() {
    echo "🐳 Running Home Assistant in Docker..."
    docker-compose --profile devhass up -d
    echo "   → Home Assistant: http://localhost:8123"
    echo "   → Debugger: localhost:5678"
    echo "   → Logs: docker-compose logs -f devhass"
}

cmd_docker_clean() {
    echo "🐳 Cleaning Docker containers and volumes..."
    docker-compose down --volumes --remove-orphans
    docker volume rm ha-bragerone-venv ha-bragerone-uv-cache ha-hass-config ha-devhass-config 2>/dev/null || true
    echo "✅ Docker cleanup complete"
}

cmd_build() {
    echo "📦 Building package..."
    uv run --group dev hatch build
    echo "✅ Package built in dist/"
}

cmd_clean() {
    echo "🧹 Cleaning build artifacts and cache..."
    rm -rf dist/ build/ *.egg-info/
    rm -rf .mypy_cache/ .pytest_cache/ .ruff_cache/
    rm -rf htmlcov/ .coverage coverage.xml
    rm -rf requirements-*.txt
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    echo "✅ Cleanup complete"
}

# Main command dispatcher
case "${1:-help}" in
    setup)        cmd_setup ;;
    test)         cmd_test ;;
    test-cov)     cmd_test_cov ;;
    lint)         cmd_lint ;;
    format)       cmd_format ;;
    typecheck)    cmd_typecheck ;;
    validate)     cmd_validate ;;
    pre-commit)   cmd_pre_commit ;;
    hass)         cmd_hass ;;
    hass-debug)   cmd_hass_debug ;;
    hass-demo)    cmd_hass_demo ;;
    docker-dev)   cmd_docker_dev ;;
    docker-hass)  cmd_docker_hass ;;
    docker-clean) cmd_docker_clean ;;
    build)        cmd_build ;;
    clean)        cmd_clean ;;
    help|--help|-h) show_usage ;;
    *)
        echo "❌ Unknown command: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac