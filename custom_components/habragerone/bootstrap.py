"""Bootstrap helpers for one-time metadata extraction and caching."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict

from .const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENUM_MAP,
    CONF_MODULES_META,
    CONF_OPTIONS,
    CONF_PLATFORM,
    CONF_RAW_TO_LABEL,
)

if TYPE_CHECKING:
    from pybragerone import BragerOneApiClient

LOGGER = logging.getLogger(__name__)


class EntityDescriptor(TypedDict, total=False):
    """Serialized descriptor for one HA entity candidate."""

    key: str
    symbol: str
    devid: str
    module_name: str
    module_title: str
    module_version: str
    device_menu: int
    label: str
    unit: str | dict[str, str] | None
    pool: str | None
    idx: int | None
    chan: str | None
    min: Any
    max: Any
    mapping: dict[str, Any] | None
    writable: bool
    platform: str
    options: list[str]
    enum_map: dict[str, str | int | float | bool]
    raw_to_label: dict[str, str]


def _coerce_raw(value: Any) -> str | int | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    if text.casefold() in {"true", "false"}:
        return text.casefold() == "true"
    try:
        numeric = int(text)
        return numeric
    except ValueError:
        pass
    try:
        numeric_float = float(text)
        return numeric_float
    except ValueError:
        return text


def _infer_platform(*, writable: bool, mapping: dict[str, Any] | None, minimum: Any, maximum: Any, symbol: str) -> str:
    symbol_norm = symbol.upper()
    component_type = str(mapping.get("component_type") if isinstance(mapping, dict) else "").lower()

    if symbol_norm.startswith("STATUS_") or "status" in component_type:
        return "binary_sensor"

    if not writable:
        return "sensor"

    values = mapping.get("values") if isinstance(mapping, dict) else None
    if isinstance(values, list) and values:
        return "select"

    if isinstance(minimum, int | float) and isinstance(maximum, int | float):
        return "number"

    if "switch" in component_type or "toggle" in component_type or symbol_norm.startswith("STATUS_"):
        return "switch"

    if "button" in component_type or "action" in component_type:
        return "button"

    return "switch"


def _enum_maps(mapping: dict[str, Any] | None) -> tuple[dict[str, str | int | float | bool], dict[str, str]]:
    if not isinstance(mapping, dict):
        return {}, {}

    units_source = mapping.get("units_source")
    values = mapping.get("values")

    enum_map: dict[str, str | int | float | bool] = {}
    raw_to_label: dict[str, str] = {}

    if isinstance(units_source, Mapping):
        if isinstance(values, list) and values:
            for raw in values:
                raw_coerced = _coerce_raw(raw)
                label_raw = units_source.get(raw)
                if label_raw is None:
                    label_raw = units_source.get(str(raw))
                label = str(label_raw).strip() if label_raw is not None else str(raw).strip()
                if not label:
                    continue
                enum_map[label] = raw_coerced
                raw_to_label[str(raw_coerced)] = label
        else:
            for raw_key, label_raw in units_source.items():
                label = str(label_raw).strip()
                raw_coerced = _coerce_raw(raw_key)
                if not label:
                    continue
                enum_map[label] = raw_coerced
                raw_to_label[str(raw_coerced)] = label
        return enum_map, raw_to_label

    if isinstance(values, list):
        for raw in values:
            raw_coerced = _coerce_raw(raw)
            label = str(raw).strip()
            if not label:
                continue
            enum_map[label] = raw_coerced
            raw_to_label[str(raw_coerced)] = label
    return enum_map, raw_to_label


def _extract_options(mapping: dict[str, Any] | None) -> list[str]:
    enum_map, _ = _enum_maps(mapping)
    return list(enum_map.keys())


class BootstrapPayload(TypedDict):
    """Container persisted in ConfigEntry data for fast startup."""

    entity_descriptors: list[EntityDescriptor]
    modules_meta: dict[str, dict[str, Any]]


async def async_build_bootstrap_payload(
    *,
    api: BragerOneApiClient,
    object_id: int,
    modules: list[str],
) -> BootstrapPayload:
    """Build one-time cached descriptors from menu/assets + prime snapshot."""
    from pybragerone.models.param import ParamStore
    from pybragerone.models.param_resolver import ParamResolver

    selected = set(modules)
    all_modules = await api.get_modules(object_id)
    effective_modules = [module for module in all_modules if not selected or module.devid in selected]

    store = ParamStore()
    resolver = ParamResolver.from_api(api=api, store=store)

    prime_result = await api.modules_parameters_prime([module.devid for module in effective_modules], return_data=True)
    if isinstance(prime_result, tuple) and len(prime_result) == 2:
        st, data = prime_result
        if st in (200, 204) and isinstance(data, dict):
            store.ingest_prime_payload(data)

    permissions = [permission.name for permission in await api.get_object_permissions(object_id)]

    per_module_symbols: dict[str, set[str]] = {}
    all_symbols: set[str] = set()

    for module in effective_modules:
        try:
            menu = await resolver.get_module_menu(module.deviceMenu, permissions=permissions)
        except Exception:
            LOGGER.debug("Menu fetch failed for %s, retrying without permissions", module.devid, exc_info=True)
            menu = await resolver.get_module_menu(module.deviceMenu, permissions=None)
        symbols = menu.all_tokens()
        per_module_symbols[module.devid] = symbols
        all_symbols.update(symbols)

    details = await resolver.describe_symbols(sorted(all_symbols))

    descriptors: list[EntityDescriptor] = []
    modules_meta: dict[str, dict[str, Any]] = {}

    for module in effective_modules:
        modules_meta[module.devid] = {
            "name": module.name,
            "title": module.moduleTitle,
            "version": module.moduleVersion,
            "gateway": module.gateway.model_dump(mode="json"),
            "device_menu": module.deviceMenu,
            "module_interface": module.moduleInterface,
            "module_address": module.moduleAddress,
        }

        for symbol in sorted(per_module_symbols.get(module.devid, set())):
            payload = details.get(symbol)
            if payload is None:
                continue

            mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else None
            writable = bool(mapping and mapping.get("command_rules"))
            label = str(payload.get("label")) if isinstance(payload.get("label"), str) else symbol

            descriptor: EntityDescriptor = {
                "key": f"{module.devid}:{symbol}",
                "symbol": symbol,
                "devid": module.devid,
                "module_name": module.name,
                "module_title": module.moduleTitle,
                "module_version": module.moduleVersion,
                "device_menu": module.deviceMenu,
                "label": label,
                "unit": payload.get("unit"),
                "pool": payload.get("pool"),
                "idx": payload.get("idx"),
                "chan": payload.get("chan"),
                "min": payload.get("min"),
                "max": payload.get("max"),
                "mapping": mapping,
                "writable": writable,
            }
            enum_map, raw_to_label = _enum_maps(mapping)
            descriptor[CONF_OPTIONS] = _extract_options(mapping)
            descriptor[CONF_ENUM_MAP] = enum_map
            descriptor[CONF_RAW_TO_LABEL] = raw_to_label
            descriptor[CONF_PLATFORM] = _infer_platform(
                writable=writable,
                mapping=mapping,
                minimum=payload.get("min"),
                maximum=payload.get("max"),
                symbol=symbol,
            )
            descriptors.append(descriptor)

    return {
        CONF_ENTITY_DESCRIPTORS: descriptors,
        CONF_MODULES_META: modules_meta,
    }
