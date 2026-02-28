"""Constants for the BragerOne Home Assistant integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "habragerone"
PLATFORMS: Final[list[str]] = ["sensor", "binary_sensor", "switch", "number", "select", "button"]

CONF_OBJECT_ID: Final = "object_id"
CONF_MODULES: Final = "modules"
CONF_BACKEND_PLATFORM: Final = "backend_platform"
CONF_LANGUAGE: Final = "language"
CONF_ENTITY_FILTER_MODE: Final = "entity_filter_mode"
CONF_MODULE_FILTER_MODES: Final = "module_filter_modes"
FILTER_MODE_UI: Final = "ui"
FILTER_MODE_PERMISSIONS: Final = "permissions"
FILTER_MODES: Final[tuple[str, str]] = (FILTER_MODE_UI, FILTER_MODE_PERMISSIONS)
DEFAULT_ENTITY_FILTER_MODE: Final = FILTER_MODE_UI
CONF_ENTITY_DESCRIPTORS: Final = "entity_descriptors"
CONF_MODULES_META: Final = "modules_meta"
CONF_PLATFORM: Final = "platform"
CONF_OPTIONS: Final = "options"
CONF_ENUM_MAP: Final = "enum_map"
CONF_RAW_TO_LABEL: Final = "raw_to_label"

DATA_API: Final = "api"
DATA_GATEWAY: Final = "gateway"
DATA_STORE: Final = "store"
DATA_RUNTIME: Final = "runtime"
DATA_ENTITY_STATS: Final = "entity_stats"
DATA_DIAGNOSTIC_TREND: Final = "diagnostic_trend"
