# BragerOne

Home Assistant custom integration for BragerOne web service.

## Description

This custom component provides integration between Home Assistant and the BragerOne system, allowing you to monitor and control your devices through the Home Assistant interface.

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
4. Click "Add Integration" and search for "BragerOne"

### HACS Installation

1. Add this repository to HACS as a custom repository
2. Install via HACS
3. Restart Home Assistant
4. Configure the integration

## Configuration

The integration can be configured through the Home Assistant UI. You will need:

- BragerOne server URL
- Authentication credentials
- Device selection

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md) and [Development guidelines](DEVELOPMENT.md)

## Support

For issues and questions:

- GitHub Issues: https://github.com/marpi82/ha-bragerone/issues
- Home Assistant Community: https://community.home-assistant.io/

## License

MIT License - see [LICENSE](README.md) file for details.
