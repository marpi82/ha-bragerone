# Development Scripts

This directory contains development helper scripts for ha-bragerone.

## Scripts

### setup.sh
Initial development environment setup script. Installs dependencies, sets up pre-commit hooks, creates configuration files.

```bash
./scripts/setup.sh
```

### dev.sh
Main development workflow helper with various commands:

```bash
# Show help
./scripts/dev.sh help

# Initial setup
./scripts/dev.sh setup

# Development workflow
./scripts/dev.sh validate    # Full validation (format + lint + type + test)
./scripts/dev.sh test-cov    # Tests with coverage
./scripts/dev.sh lint        # Lint and fix code
./scripts/dev.sh format      # Format code

# Home Assistant
./scripts/dev.sh hass        # Start Home Assistant
./scripts/dev.sh hass-debug  # Start with debugger (port 5678)
./scripts/dev.sh hass-demo   # Start with demo mode

# Docker
./scripts/dev.sh docker-hass # Run in Docker Compose
./scripts/dev.sh docker-clean # Clean Docker volumes

# Build and cleanup
./scripts/dev.sh build      # Build package
./scripts/dev.sh clean      # Clean artifacts
```

## Quick Start

1. **Initial setup**: `./scripts/setup.sh`
2. **Start developing**: Edit code in `custom_components/habragerone/`
3. **Test changes**: `./scripts/dev.sh validate`
4. **Test integration**: `./scripts/dev.sh hass`
5. **Before commit**: `./scripts/dev.sh pre-commit`

## Development Workflow

The typical development workflow:

1. Make changes to your custom component
2. Run `./scripts/dev.sh validate` to check code quality
3. Run `./scripts/dev.sh hass` to test with Home Assistant
4. Run tests with `./scripts/dev.sh test-cov`
5. Commit your changes (pre-commit hooks will run automatically)

## Docker Development

For isolated development environment:

```bash
# All-in-one container with Home Assistant
./scripts/dev.sh docker-hass

# Development container only
./scripts/dev.sh docker-dev
```

## Environment Variables

Create a `.env` file in the project root:

```bash
# Home Assistant configuration
HASS_CONFIG=./config
HASS_LOG_LEVEL=info

# Python debugger port
DEBUGPY_PORT=5678
```

## VS Code Integration

The scripts integrate with VS Code tasks. Use `Ctrl+Shift+P` → `Tasks: Run Task` to access:

- uv: Sync Dependencies
- HA: Run
- Tests: pytest
- Lint: ruff check
- Format: ruff format
- And many more...

## Troubleshooting

### Dependencies Not Found
Run `./scripts/dev.sh setup` to reinstall dependencies.

### py-bragerone Not Found
Ensure py-bragerone is cloned at `../py-bragerone` or adjust the path in setup scripts.

### Docker Issues
Clean Docker state: `./scripts/dev.sh docker-clean`

### Permission Issues
Make scripts executable: `chmod +x scripts/*.sh`