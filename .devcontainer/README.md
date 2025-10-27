# ha-bragerone Devcontainer

This devcontainer provides a fully configured development environment for ha-bragerone Home Assistant custom component.

## Features

- **Base image**: `python:3.13-slim-trixie`
- **Dependency management**: uv with py-bragerone as editable dependency
- **Home Assistant**: Pre-configured development instance
- **Build system**: Hatch with hatch-vcs (CalVer from git tags)
- **Pre-configured tools**: Ruff, mypy, pytest, Bandit, pip-audit
- **VS Code extensions**: Python, Pylance, Ruff, mypy-type-checker, GitLens, Copilot
- **NFS-optimized**: `.venv`, uv cache, and Home Assistant config stored in Docker volumes (not on NFS mount)
- **Port forwarding**: Home Assistant (8123) and Python debugger (5678)

## Quick Start

1. Open the project in VS Code
2. When prompted, click "Reopen in Container" (or press `F1` → `Dev Containers: Reopen in Container`)
3. Wait for the container to build and setup to complete
4. Start Home Assistant: `uv run poe hass`
5. Open http://localhost:8123 to access Home Assistant
6. Start developing your custom component!

## Environment Variables

The following environment variables are pre-configured:

- `UV_PROJECT_ENVIRONMENT=.venv` - Use project-local virtualenv
- `UV_LINK_MODE=copy` - Avoid hardlink warnings on NFS
- `RUFF_NUM_THREADS=1` - Prevent thread limit issues
- `DEBUGPY_PORT=5678` - Python debugger port
- `HASS_CONFIG=./config` - Home Assistant config directory
- `HASS_LOG_LEVEL=info` - Home Assistant log level

## Common Commands

### Development
```bash
# Run tests
uv run --group test pytest

# Lint and format
uv run --group dev poe fix

# Type check
uv run --group dev poe typecheck

# Full validation (quality + security + tests)
uv run --group dev poe validate

# Run pre-commit hooks manually
uv run --group dev pre-commit run --all-files
```

### Home Assistant
```bash
# Start Home Assistant (development mode)
uv run poe hass

# Restart Home Assistant
uv run poe hass-restart

# View logs
docker-compose logs -f homeassistant  # If using compose alternative
```

### Testing Integration
```bash
# Test with coverage
uv run --group test pytest --cov=custom_components.habragerone --cov-report=term-missing

# Test specific files
uv run --group test pytest tests/test_sensor.py
```

## Volumes and Mounts

The container uses Docker volumes to store data outside the NFS mount:

- `ha-bragerone-venv`: Python virtual environment
- `ha-bragerone-uv-cache`: uv package cache
- `ha-bragerone-hass-config`: Home Assistant configuration

This prevents NFS-related issues with file operations.

## Port Forwarding

- **8123**: Home Assistant web interface
- **5678**: Python debugger (debugpy)

## Debugging

### VS Code Debugging
The container is pre-configured for debugging with VS Code:

1. Set breakpoints in your custom component code
2. Start Home Assistant with debugger: `uv run python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m homeassistant --config config --debug`
3. Attach VS Code debugger to port 5678

### Home Assistant Integration Development

Your custom component is located in `custom_components/habragerone/`. Changes to the component code will be reflected when you restart Home Assistant.

## Configuration

### Home Assistant Configuration
Edit `config/configuration.yaml` to configure your development instance. The default configuration includes:

- Basic Home Assistant setup
- Debug logging for your custom component
- Frontend enabled

### Adding Dependencies
```bash
# Add new dependency
uv add package-name

# Add development dependency  
uv add --group dev package-name

# Add test dependency
uv add --group test package-name
```

## Troubleshooting

### py-bragerone Not Found
If py-bragerone is not found during setup:
```bash
# Add it manually (adjust path as needed)
uv add /path/to/py-bragerone --editable
```

### Permission Issues
File permissions are automatically fixed during setup. If you encounter issues:
```bash
# Fix permissions manually
sudo chown -R vscode:vscode /home/vscode/.cache .venv config
```

### Home Assistant Not Starting
Check the logs for errors:
```bash
# View Home Assistant output
uv run poe hass

# Or check specific errors
python -m homeassistant --config config --debug
```

### NFS-related Errors
If you see `Directory not empty (os error 39)`:
- Volumes are used to avoid NFS issues
- If problems persist, clean volumes:
  ```bash
  docker volume rm ha-bragerone-venv ha-bragerone-uv-cache ha-bragerone-hass-config
  ```
- Then rebuild container

### Container Build Fails
Ensure Docker is running and you have internet connectivity. The setup script installs many system dependencies required for Home Assistant.

## Development Workflow

1. **Setup**: Start the devcontainer
2. **Code**: Develop your custom component in `custom_components/habragerone/`
3. **Test**: Run `uv run --group test pytest` 
4. **Integration test**: Start Home Assistant with `uv run poe hass`
5. **Debug**: Use VS Code debugger or Home Assistant logs
6. **Validate**: Run `uv run --group dev poe validate` before committing
7. **Commit**: Pre-commit hooks will run automatically

## Custom Component Structure

```
custom_components/habragerone/
├── __init__.py          # Integration setup
├── config_flow.py       # Configuration flow
├── const.py            # Constants
├── manifest.json       # Integration manifest
├── sensor.py           # Sensor entities
├── services.yaml       # Service definitions
├── strings.json        # UI strings
└── translations/       # Internationalization
```

Make sure to update `manifest.json` with your integration's requirements and metadata.