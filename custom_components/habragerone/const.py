"""Constants for the BragerOne Home Assistant integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "habragerone"
PLATFORMS: Final[list[str]] = ["sensor", "binary_sensor", "switch", "number", "select", "button"]

CONF_OBJECT_ID: Final = "object_id"
CONF_MODULES: Final = "modules"
CONF_BACKEND_PLATFORM: Final = "backend_platform"
CONF_LANGUAGE: Final = "language"
# Deprecated (#212): entities are no longer filtered by UI/permissions mode — every
# permission-gated entity is created, with non-everyday-UI ones disabled by default
# (see CONF_ENABLED_BY_DEFAULT). Kept only so old entry data can still be read/migrated.
CONF_ENTITY_FILTER_MODE: Final = "entity_filter_mode"
CONF_MODULE_FILTER_MODES: Final = "module_filter_modes"
FILTER_MODE_UI: Final = "ui"
FILTER_MODE_PERMISSIONS: Final = "permissions"
FILTER_MODES: Final[tuple[str, str]] = (FILTER_MODE_UI, FILTER_MODE_PERMISSIONS)
DEFAULT_ENTITY_FILTER_MODE: Final = FILTER_MODE_UI
CONF_ENABLED_BY_DEFAULT: Final = "enabled_by_default"
CONF_UI_ROUTE_SYMBOL: Final = "ui_route_symbol"
CONF_ROUTE_VISIBILITY_DEPS: Final = "route_visibility_deps"
CONF_ROUTE_VISIBILITY_NAME: Final = "route_visibility_name"
CONF_ROUTE_VISIBILITY_PATH: Final = "route_visibility_path"
CONF_DEVICE_GROUPING: Final = "device_grouping"
DEVICE_GROUPING_FLAT: Final = "flat"
DEVICE_GROUPING_BY_MENU: Final = "group_by_menu"
DEVICE_GROUPING_MODES: Final[tuple[str, str]] = (DEVICE_GROUPING_FLAT, DEVICE_GROUPING_BY_MENU)
DEFAULT_DEVICE_GROUPING: Final = DEVICE_GROUPING_FLAT
CONF_ENTITY_DESCRIPTORS: Final = "entity_descriptors"
CONF_CONNECTION_DESCRIPTORS: Final = "connection_descriptors"
CONF_MODULES_META: Final = "modules_meta"
CONF_PLATFORM: Final = "platform"
CONF_OPTIONS: Final = "options"
CONF_ENUM_MAP: Final = "enum_map"
CONF_RAW_TO_LABEL: Final = "raw_to_label"
CONF_BOOTSTRAP_DEBUG: Final = "bootstrap_debug"
CONF_BOOTSTRAP_VERSION: Final = "bootstrap_version"
CONF_UPSTREAM_ASSETS_FINGERPRINT: Final = "upstream_assets_fingerprint"
BOOTSTRAP_VERSION: Final = 14

# Stable non-menu source key for module connectivity (SPA ``module.connection.*`` i18n).
# Kept separate from menu-router paths so HA #165 can place these on a child device.
CONNECTION_MENU_KEY: Final = "module.connection"

DATA_API: Final = "api"
DATA_GATEWAY: Final = "gateway"
DATA_STORE: Final = "store"
DATA_RUNTIME: Final = "runtime"
DATA_ENTITY_STATS: Final = "entity_stats"
DATA_DIAGNOSTIC_TREND: Final = "diagnostic_trend"
