# BragerOne

Home Assistant custom integration for BragerOne web service.

**Status:** Stable (Production/Stable)

## Description

This custom component provides integration between Home Assistant and the BragerOne system, allowing you to monitor and control your devices through the Home Assistant interface.

## Features

- Real-time parameter monitoring
- Device control via Home Assistant
- Configurable through Home Assistant UI
- Support for multiple device types
- Per-module cloud connectivity diagnostic (SPA `connectedAt` / `module.connection.*` labels) on a **separate** child device (`{devid}:module.connection`, linked with `via_device`); this is intentional in **flat** and group-by-menu alike — parameter entities go unavailable when the module is offline; writes are refused while offline. Module offline is observe-only (wait for the plant to reconnect).
- Separate **Cloud API session** diagnostic (library↔cloud Socket.IO) on a config-entry service device — detectable and self-healing; never folded into module `connectedAt`. Config-entry diagnostics include `last_param_update_age_s` (seconds since the last parameter snapshot/delta) to distinguish a live session from a frozen push stream.
- Optional device grouping by menu (options: flat default vs group-by-menu child devices per **parent** menu route with `via_device`)

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

Testers: enable HACS **Show beta versions** to install `alpha` / `beta` / `rc` tags before they hit the default (stable) channel. Maintainers always smoke-test a pre-release on a live HA instance before cutting the matching stable tag — see [DEVELOPMENT.md](DEVELOPMENT.md#publishing-releases).

## Configuration

The integration can be configured through the Home Assistant UI. You will need:

- BragerOne / TiSConnect credentials and backend platform
- Installation and module selection
- Entity filtering mode (UI menu vs permissions)
- Device grouping (flat = one HA device per internet module for parameter entities; group by menu = child devices per **parent** menu route, linked via the module — remaps device membership when changed). In **both** modes the connectivity diagnostic stays on a separate `{devid}:module.connection` child (`via_device`), so it is not folded into the module device in flat mode.

## Contributions are welcome!

If you want to contribute to this, please read the [Contributing guidelines](CONTRIBUTING.md) and [Development guidelines](DEVELOPMENT.md). Use the [issue forms](https://github.com/marpi82/ha-bragerone/issues/new/choose) and the pull request template.

## Support

For issues and questions:

- GitHub Issues (templated): https://github.com/marpi82/ha-bragerone/issues/new/choose
- Home Assistant Community: https://community.home-assistant.io/

Do **not** file security issues publicly — see [SECURITY.md](SECURITY.md).

## License

MIT License - see [LICENSE](LICENSE) file for details.
