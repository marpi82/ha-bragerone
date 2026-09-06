# BragerOne

[![Release](https://img.shields.io/github/v/release/marpi82/ha-bragerone?include_prereleases&label=release)](https://github.com/marpi82/ha-bragerone/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/marpi82/ha-bragerone/ci.yml?branch=main&label=CI)](https://github.com/marpi82/ha-bragerone/actions/workflows/ci.yml)
[![HA Integration](https://img.shields.io/github/actions/workflow/status/marpi82/ha-bragerone/ha-integration-test.yml?branch=main&label=HA%20integration)](https://github.com/marpi82/ha-bragerone/actions/workflows/ha-integration-test.yml)
[![HACS](https://img.shields.io/github/actions/workflow/status/marpi82/ha-bragerone/hacs.yml?branch=main&label=HACS)](https://github.com/marpi82/ha-bragerone/actions/workflows/hacs.yml)
[![Codecov](https://codecov.io/gh/marpi82/ha-bragerone/graph/badge.svg)](https://codecov.io/gh/marpi82/ha-bragerone)
[![License](https://img.shields.io/github/license/marpi82/ha-bragerone)](https://github.com/marpi82/ha-bragerone/blob/main/LICENSE)
[![Renovate](https://img.shields.io/badge/renovate-enabled-blue?logo=renovate&logoColor=white)](https://app.renovatebot.com/dashboard)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-%E2%89%A52026.3.0-blue)](https://www.home-assistant.io/)

Home Assistant custom integration for BragerOne web service.

**Status:** Stable (Production/Stable)

## Description

This custom component provides integration between Home Assistant and the BragerOne system, allowing you to monitor and control your devices through the Home Assistant interface.

## Features

- Real-time parameter monitoring
- Device control via Home Assistant
- Configurable through Home Assistant UI
- Support for multiple device types
- Per-module cloud connectivity diagnostic (SPA `connectedAt` / `module.connection.*` labels) on the **internet-module** device together with alarms/activity diagnostics — in **flat** mode all entities share that device; in **group-by-menu** mode parameter entities sit on menu child devices linked to the parent module while connectivity, alarms, and activity stay on the parent module device. Parameter entities go unavailable when the module is offline; writes are refused while offline. Module offline is observe-only (wait for the plant to reconnect). Connectivity and cloud-session binary sensors expose outage attributes (`down_since` / `down_for_s` / `reason` while down; `last_down_for_s` / `last_reason` after restore) — `reason` is the client observation source, not plant hardware diagnosis. The cloud-session sensor also exposes live-push health (`push_healthy` / `live_stale_for_s` / `last_resumed_after_s`) when Socket.IO is up but parameter pushes go stale — that does **not** change the binary `on/off` meaning.
- Separate **Cloud API session** diagnostic (library↔cloud Socket.IO) on a config-entry service device — detectable and self-healing; never folded into module `connectedAt`. Config-entry diagnostics include `last_param_update_age_s` / `last_live_param_update_age_s` (seconds since the last parameter snapshot/delta) to distinguish a live session from a frozen push stream, plus a short `connectivity_episodes` ring buffer of recent completed cloud / module / live-stale outages (library default ~20; not long-term history).
- Optional device grouping by menu (options: flat default vs group-by-menu child devices per **parent** menu route linked to the parent module)
- Everyday-UI menu routes (including static SPA shells such as **Strefy czasowe**) map to panel groups and, in group-by-menu mode, child devices; UI-route entities respect SPA route visibility at runtime (`available`) without changing entity-registry enable state

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

Testers: enable HACS **Show beta versions** to install `alpha` / `beta` / `rc` tags before they hit the default (stable) channel. Maintainers always smoke-test a pre-release on a live HA instance before cutting the matching stable tag — see [DEVELOPMENT.md](DEVELOPMENT.md#publishing-releases). Field-testing a **library** pre-release on HassOS uses a PyPI pin (not `git+`); see [DEVELOPMENT.md](DEVELOPMENT.md#field-testing-a-library-pre-release-on-hassos-275).

## Configuration

The integration can be configured through the Home Assistant UI. You will need:

- BragerOne / TiSConnect credentials and backend platform
- Installation and module selection
- Device grouping (flat = one HA device per internet module for parameters, connectivity, alarms, and activity; group by menu = parameter entities on child devices per **parent** menu route linked to the parent module, while connectivity/alarms/activity stay on the parent module — remaps device membership when changed).

After upgrading to a release that bumps `BOOTSTRAP_VERSION` (currently **14** for static menu routes / #192), reload the integration or re-add it so entity descriptors pick up new menu metadata.

Every permission-gated parameter becomes an entity — there is no separate UI/permissions filtering mode to choose. Entities that are outside the everyday BragerOne web UI (installer-only panels, or panels the SPA itself hides) are still created, but start **disabled** in the entity registry; enable them manually if you need them. Enable/disable state can be changed per-entity at any time from the entity registry.

## Contributions are welcome!

If you want to contribute to this, please read the [Contributing guidelines](CONTRIBUTING.md) and [Development guidelines](DEVELOPMENT.md). Use the [issue forms](https://github.com/marpi82/ha-bragerone/issues/new/choose) and the pull request template.

## Support

For issues and questions:

- GitHub Issues (templated): https://github.com/marpi82/ha-bragerone/issues/new/choose
- Home Assistant Community: https://community.home-assistant.io/

Do **not** file security issues publicly — see [SECURITY.md](SECURITY.md).

## License

MIT License - see [LICENSE](LICENSE) file for details.
