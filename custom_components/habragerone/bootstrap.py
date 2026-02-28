"""Bootstrap helpers for one-time metadata extraction and caching."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

from .const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENTITY_FILTER_MODE,
    CONF_ENUM_MAP,
    CONF_MODULE_FILTER_MODES,
    CONF_MODULES_META,
    CONF_OPTIONS,
    CONF_PLATFORM,
    CONF_RAW_TO_LABEL,
    DEFAULT_ENTITY_FILTER_MODE,
    FILTER_MODE_PERMISSIONS,
    FILTER_MODE_UI,
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
    panel_path: str
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


_SWITCHISH_RULE_VALUES = {"0", "1", "true", "false", "on", "off", "enabled", "disabled", "yes", "no"}
_NON_ENTITY_COMPONENT_MARKERS = ("password", "menu", "view", "separator", "title")


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


def _has_direct_address(*, pool: Any, chan: Any, idx: Any) -> bool:
    return isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int)


def _is_switch_like_command(mapping: dict[str, Any] | None) -> bool:
    if not isinstance(mapping, dict):
        return False

    command_rules = mapping.get("command_rules")
    if not isinstance(command_rules, list) or not command_rules:
        return False

    logic_tags: set[str] = set()
    raw_values: set[str] = set()

    for candidate in command_rules:
        if not isinstance(candidate, dict):
            continue
        logic = candidate.get("logic")
        if isinstance(logic, str) and logic.strip():
            logic_tags.add(logic.strip().casefold())
        value = candidate.get("value")
        if isinstance(value, bool):
            raw_values.add("true" if value else "false")
        elif isinstance(value, int | float):
            raw_values.add(str(int(value)) if float(value).is_integer() else str(value).casefold())
        elif isinstance(value, str):
            raw_values.add(value.strip().casefold())

    if {"on", "off"}.issubset(logic_tags):
        return True

    return bool(raw_values and raw_values.issubset(_SWITCHISH_RULE_VALUES))


def _is_exposable_descriptor(
    *,
    writable: bool,
    pool: Any,
    chan: Any,
    idx: Any,
    mapping: dict[str, Any] | None,
) -> bool:
    component_type = str(mapping.get("component_type") if isinstance(mapping, dict) else "").strip().lower()
    if component_type and any(marker in component_type for marker in _NON_ENTITY_COMPONENT_MARKERS):
        return False
    return writable or _has_direct_address(pool=pool, chan=chan, idx=idx)


def _infer_platform(
    *,
    writable: bool,
    mapping: dict[str, Any] | None,
    minimum: Any,
    maximum: Any,
    symbol: str,
    chan: Any,
    has_direct_address: bool,
) -> str:
    symbol_norm = symbol.upper()
    component_type = str(mapping.get("component_type") if isinstance(mapping, dict) else "").lower()

    if chan == "s" or symbol_norm.startswith("STATUS_") or "status" in component_type:
        return "binary_sensor"

    if not writable:
        return "sensor"

    values = mapping.get("values") if isinstance(mapping, dict) else None
    if isinstance(values, list) and values:
        return "select"

    if "button" in component_type or "action" in component_type:
        return "button"

    if not has_direct_address:
        return "button"

    if isinstance(minimum, int | float) and isinstance(maximum, int | float):
        return "number"

    if "switch" in component_type or "toggle" in component_type or _is_switch_like_command(mapping):
        return "switch"

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


def _collect_symbols_from_route(route: Any) -> set[str]:
    symbols: set[str] = set()

    def add_from_container(container: Any) -> None:
        if container is None:
            return
        for kind in ("read", "write", "status", "special"):
            items = getattr(container, kind, None)
            if not isinstance(items, list):
                continue
            for item in items:
                token = getattr(item, "token", None)
                if isinstance(token, str) and token:
                    symbols.add(token)

    meta = getattr(route, "meta", None)
    if meta is not None:
        add_from_container(getattr(meta, "parameters", None))
    add_from_container(getattr(route, "parameters", None))
    return symbols


def _collect_symbols_from_menu(menu: Any) -> set[str]:
    symbols: set[str] = set()
    stack = list(getattr(menu, "routes", []) or [])[::-1]
    while stack:
        route = stack.pop()
        symbols.update(_collect_symbols_from_route(route))
        children = getattr(route, "children", None)
        if isinstance(children, list):
            for child in reversed(children):
                stack.append(child)
    return symbols


def _normalize_filter_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in {FILTER_MODE_UI, FILTER_MODE_PERMISSIONS}:
        return mode
    return DEFAULT_ENTITY_FILTER_MODE


def _has_display_value(*, value: Any, value_label: Any) -> bool:
    if isinstance(value_label, str) and value_label.strip():
        return True
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def normalize_cached_descriptors(descriptors_raw: list[Any]) -> list[EntityDescriptor]:
    """Normalize and filter cached descriptors to ensure valid platform assignment."""
    normalized: list[EntityDescriptor] = []

    for descriptor_raw in descriptors_raw:
        if not isinstance(descriptor_raw, dict):
            continue

        descriptor = cast(EntityDescriptor, dict(descriptor_raw))
        symbol = str(descriptor.get("symbol") or "")
        pool = descriptor.get("pool")
        chan = descriptor.get("chan")
        idx = descriptor.get("idx")
        mapping = descriptor.get("mapping") if isinstance(descriptor.get("mapping"), dict) else None
        writable = bool(descriptor.get("writable")) or bool(mapping and mapping.get("command_rules"))

        if not _is_exposable_descriptor(writable=writable, pool=pool, chan=chan, idx=idx, mapping=mapping):
            continue

        enum_map, raw_to_label = _enum_maps(mapping)
        descriptor["writable"] = writable
        descriptor[CONF_OPTIONS] = list(enum_map.keys())
        descriptor[CONF_ENUM_MAP] = enum_map
        descriptor[CONF_RAW_TO_LABEL] = raw_to_label
        descriptor[CONF_PLATFORM] = _infer_platform(
            writable=writable,
            mapping=mapping,
            minimum=descriptor.get("min"),
            maximum=descriptor.get("max"),
            symbol=symbol,
            chan=chan,
            has_direct_address=_has_direct_address(pool=pool, chan=chan, idx=idx),
        )
        normalized.append(descriptor)

    return normalized


class BootstrapPayload(TypedDict):
    """Container persisted in ConfigEntry data for fast startup."""

    entity_descriptors: list[EntityDescriptor]
    modules_meta: dict[str, dict[str, Any]]
    entity_filter_mode: str
    module_filter_modes: dict[str, str]


async def async_build_bootstrap_payload(
    *,
    api: BragerOneApiClient,
    object_id: int,
    modules: list[str],
    language: str | None = None,
    entity_filter_mode: str = DEFAULT_ENTITY_FILTER_MODE,
    module_filter_modes: dict[str, str] | None = None,
) -> BootstrapPayload:
    """Build one-time cached descriptors from menu/assets + prime snapshot."""
    from pybragerone.models.param import ParamStore
    from pybragerone.models.param_resolver import ParamResolver

    selected = set(modules)
    all_modules = await api.get_modules(object_id)
    effective_modules = [module for module in all_modules if not selected or module.devid in selected]

    store = ParamStore()
    resolver = ParamResolver.from_api(api=api, store=store, lang=language)
    filter_mode = _normalize_filter_mode(entity_filter_mode)
    normalized_module_modes = {
        str(devid): _normalize_filter_mode(mode) for devid, mode in (module_filter_modes or {}).items() if str(devid).strip()
    }

    prime_result = await api.modules_parameters_prime([module.devid for module in effective_modules], return_data=True)
    if isinstance(prime_result, tuple) and len(prime_result) == 2:
        st, data = prime_result
        if st in (200, 204) and isinstance(data, dict):
            store.ingest_prime_payload(data)

    per_module_candidate_symbols: dict[str, set[str]] = {}
    per_module_panel_paths: dict[str, dict[str, str]] = {}
    all_candidate_symbols: set[str] = set()

    for module in effective_modules:
        module_permissions = [str(perm) for perm in getattr(module, "permissions", []) or []]
        symbols: set[str] = set()
        panel_paths: dict[str, str] = {}

        try:
            groups = await resolver.build_panel_groups(
                device_menu=module.deviceMenu,
                permissions=module_permissions,
                all_panels=True,
            )
        except Exception:
            LOGGER.debug("Panel-group build failed for %s, retrying without permissions", module.devid, exc_info=True)
            groups = await resolver.build_panel_groups(
                device_menu=module.deviceMenu,
                permissions=None,
                all_panels=True,
            )

        symbols = {symbol for panel_symbols in groups.values() for symbol in panel_symbols if symbol}
        for panel_name, panel_symbols in groups.items():
            panel_title = str(panel_name).strip()
            if not panel_title:
                continue
            for symbol in panel_symbols:
                if isinstance(symbol, str) and symbol and symbol not in panel_paths:
                    panel_paths[symbol] = panel_title

        per_module_candidate_symbols[module.devid] = symbols
        per_module_panel_paths[module.devid] = panel_paths
        all_candidate_symbols.update(symbols)

    details = await resolver.describe_symbols(sorted(all_candidate_symbols))
    flat_values = store.flatten()
    per_module_symbols: dict[str, set[str]] = {}

    for module in effective_modules:
        module_symbols: set[str] = set()
        devid_text = str(module.devid)
        module_mode = normalized_module_modes.get(devid_text, filter_mode)
        resolver.set_runtime_context(
            {
                "devid": devid_text,
                "modulesMap": {
                    devid_text: {
                        "connectedAt": module.connectedAt,
                    }
                },
            }
        )

        for symbol in per_module_candidate_symbols.get(module.devid, set()):
            payload = details.get(symbol)
            if payload is None:
                continue
            try:
                resolved = await resolver.resolve_value(symbol)
                if not _has_display_value(value=resolved.value, value_label=resolved.value_label):
                    continue

                if module_mode == FILTER_MODE_UI:
                    visible, _ = resolver.parameter_visibility_diagnostics(
                        desc=payload,
                        resolved=resolved,
                        flat_values=flat_values,
                    )
                else:
                    visible = True
            except Exception:
                LOGGER.debug("Visibility diagnostics failed for %s/%s", module.devid, symbol, exc_info=True)
                visible = True

            if visible:
                module_symbols.add(symbol)

        per_module_symbols[module.devid] = module_symbols

    resolver.set_runtime_context(None)

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
                "panel_path": per_module_panel_paths.get(module.devid, {}).get(symbol, ""),
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

            if not _is_exposable_descriptor(
                writable=writable,
                pool=descriptor.get("pool"),
                chan=descriptor.get("chan"),
                idx=descriptor.get("idx"),
                mapping=mapping,
            ):
                continue

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
                chan=payload.get("chan"),
                has_direct_address=_has_direct_address(
                    pool=payload.get("pool"),
                    chan=payload.get("chan"),
                    idx=payload.get("idx"),
                ),
            )
            descriptors.append(descriptor)

    return {
        CONF_ENTITY_DESCRIPTORS: descriptors,
        CONF_MODULES_META: modules_meta,
        CONF_ENTITY_FILTER_MODE: filter_mode,
        CONF_MODULE_FILTER_MODES: {
            str(module.devid): normalized_module_modes.get(str(module.devid), filter_mode) for module in effective_modules
        },
    }
