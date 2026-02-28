# Ha-BragerOne

Home Assistant custom integration for Brager One web service.

## Description

This custom component provides integration between Home Assistant and the Brager One system, allowing you to monitor and control your devices through the Home Assistant interface.

## Features

- Real-time parameter monitoring
- Device control via Home Assistant
- Configurable through Home Assistant UI
- Support for multiple device types

## Installation

### Manual Installation

1. Copy the `custom_components/habragerone` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Configuration > Integrations
4. Click "Add Integration" and search for "Brager One"

### HACS Installation

1. Add this repository to HACS as a custom repository
2. Install via HACS
3. Restart Home Assistant
4. Configure the integration

## Configuration

The integration can be configured through the Home Assistant UI. You will need:

- Brager One server URL
- Authentication credentials
- Device selection

## Development

This project uses:

- Python 3.13+
- uv for dependency management
- pre-commit for code quality
- Docker Compose for development environment
- Trusted Publisher for PyPI publishing

### Setup Development Environment

```bash
# Install dependencies
uv sync --group dev --group test

# Install pre-commit hooks  
uv run pre-commit install

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

### Publishing Releases

The project automatically publishes to PyPI using GitHub Actions:

```bash
# Create stable release
./scripts/release.sh 2025.1.0

# Create pre-release
./scripts/release.sh 2025.1.0 alpha  # or beta, rc
```

Releases are automatically published to:
- **PyPI** for stable releases (`v2025.1.0`)
- **TestPyPI** for pre-releases (`v2025.1.0a1`, `v2025.1.0b1`, `v2025.1.0rc1`)

See [PyPI Setup Guide](docs/PYPI_SETUP.md) for Trusted Publisher configuration.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Support

For issues and questions:

- GitHub Issues: https://github.com/marpi82/ha-bragerone/issues
- Home Assistant Community: https://community.home-assistant.io/