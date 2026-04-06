"""Bootstrap helpers for one-time metadata extraction and caching."""

from __future__ import annotations

import logging
import re
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
    menu_kinds: list[str]


_SWITCHISH_RULE_VALUES = {"0", "1", "true", "false", "on", "off", "enabled", "disabled", "yes", "no"}
_NON_ENTITY_COMPONENT_MARKERS = ("password", "menu", "view", "separator", "title")
_PARAM_KINDS = ("read", "write", "status", "special")
_SYMBOL_TOKEN_RE = re.compile(r"^(?:COMMAND_|URUCHOMIENIE_|PARAM_|STATUS_)[A-Z0-9_]+$")


def _get_field(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_symbol_token(value: Any, *, _depth: int = 0) -> str | None:
    if _depth > 3:
        return None
    if isinstance(value, str):
        token = value.strip()
        if _SYMBOL_TOKEN_RE.match(token):
            return token
        return None
    if isinstance(value, Mapping):
        direct = value.get("token")
        if isinstance(direct, str):
            token = direct.strip()
            if _SYMBOL_TOKEN_RE.match(token):
                return token
        nested = value.get("parameter")
        nested_token = _extract_symbol_token(nested, _depth=_depth + 1)
        if nested_token:
            return nested_token
        for key in ("symbol", "name", "raw"):
            nested_token = _extract_symbol_token(value.get(key), _depth=_depth + 1)
            if nested_token:
                return nested_token
        return None

    token_attr = getattr(value, "token", None)
    if isinstance(token_attr, str):
        token = token_attr.strip()
        if _SYMBOL_TOKEN_RE.match(token):
            return token
    nested_attr = getattr(value, "parameter", None)
    nested_token = _extract_symbol_token(nested_attr, _depth=_depth + 1)
    if nested_token:
        return nested_token
    for attr in ("symbol", "name", "raw"):
        nested_token = _extract_symbol_token(getattr(value, attr, None), _depth=_depth + 1)
        if nested_token:
            return nested_token
    return None


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
    unit: Any,
) -> str:
    symbol_norm = symbol.upper()
    component_type = str(mapping.get("component_type") if isinstance(mapping, dict) else "").lower()

    if (chan == "s" or symbol_norm.startswith("STATUS_") or "status" in component_type) and not writable:
        return "binary_sensor"

    if not writable:
        return "sensor"

    values = mapping.get("values") if isinstance(mapping, dict) else None
    if isinstance(values, list) and values:
        return "select"

    if isinstance(unit, Mapping) and unit:
        return "select"

    if "button" in component_type or "action" in component_type:
        return "button"

    if not has_direct_address:
        return "button"

    if isinstance(minimum, int | float) and isinstance(maximum, int | float):
        return "number"

    if "switch" in component_type or "toggle" in component_type or _is_switch_like_command(mapping):
        return "switch"

    if chan == "v":
        return "number"

    return "switch"


def _enum_maps(
    mapping: dict[str, Any] | None,
    *,
    descriptor_unit: Any | None = None,
) -> tuple[dict[str, str | int | float | bool], dict[str, str]]:
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

    if isinstance(descriptor_unit, Mapping):
        for raw, label_raw in descriptor_unit.items():
            label = str(label_raw).strip()
            raw_coerced = _coerce_raw(raw)
            if not label:
                continue
            enum_map[label] = raw_coerced
            raw_to_label[str(raw_coerced)] = label
    return enum_map, raw_to_label


def _extract_options(mapping: dict[str, Any] | None, *, descriptor_unit: Any | None = None) -> list[str]:
    enum_map, _ = _enum_maps(mapping, descriptor_unit=descriptor_unit)
    return list(enum_map.keys())


def _collect_symbols_from_route(route: Any) -> set[str]:
    symbols: set[str] = set()

    def token_from_item(item: Any) -> str | None:
        return _extract_symbol_token(item)

    def add_from_container(container: Any) -> None:
        if container is None:
            return
        for kind in ("read", "write", "status", "special"):
            items = _get_field(container, kind)
            if not isinstance(items, list):
                continue
            for item in items:
                token = token_from_item(item)
                if isinstance(token, str) and token:
                    symbols.add(token)

    meta = _get_field(route, "meta")
    if meta is not None:
        add_from_container(_get_field(meta, "parameters"))
    add_from_container(_get_field(route, "parameters"))
    return symbols


def _collect_symbol_kinds_from_route(route: Any) -> dict[str, set[str]]:
    symbol_kinds: dict[str, set[str]] = {}

    def token_from_item(item: Any) -> str | None:
        return _extract_symbol_token(item)

    def add_from_container(container: Any) -> None:
        if container is None:
            return
        for kind in _PARAM_KINDS:
            items = _get_field(container, kind)
            if not isinstance(items, list):
                continue
            for item in items:
                token = token_from_item(item)
                if isinstance(token, str) and token:
                    symbol_kinds.setdefault(token, set()).add(kind)

    meta = _get_field(route, "meta")
    if meta is not None:
        add_from_container(_get_field(meta, "parameters"))
    add_from_container(_get_field(route, "parameters"))
    return symbol_kinds


def _collect_symbol_kinds_from_menu(menu: Any) -> dict[str, set[str]]:
    symbol_kinds: dict[str, set[str]] = {}
    stack = list(_get_field(menu, "routes") or [])[::-1]
    while stack:
        route = stack.pop()
        route_kinds = _collect_symbol_kinds_from_route(route)
        for symbol, kinds in route_kinds.items():
            symbol_kinds.setdefault(symbol, set()).update(kinds)
        children = _get_field(route, "children")
        if isinstance(children, list):
            for child in reversed(children):
                stack.append(child)
    return symbol_kinds


def _collect_symbols_from_menu(menu: Any) -> set[str]:
    symbols: set[str] = set()
    stack = list(_get_field(menu, "routes") or [])[::-1]
    while stack:
        route = stack.pop()
        symbols.update(_collect_symbols_from_route(route))
        children = _get_field(route, "children")
        if isinstance(children, list):
            for child in reversed(children):
                stack.append(child)
    return symbols


def _normalize_filter_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in {FILTER_MODE_UI, FILTER_MODE_PERMISSIONS}:
        return mode
    return DEFAULT_ENTITY_FILTER_MODE


def _normalize_panel_path(panel_path: str) -> str:
    return panel_path.strip()


def _has_display_value(*, value: Any, value_label: Any) -> bool:
    if isinstance(value_label, str) and value_label.strip():
        return True
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_command_like_symbol(symbol: str) -> bool:
    token = symbol.strip().upper()
    if not token:
        return False
    if token.startswith(("COMMAND_", "URUCHOMIENIE_")):
        return True
    return "RESTART" in token and "MODULE" in token


def _has_named_command_rule(mapping: dict[str, Any] | None) -> bool:
    if not isinstance(mapping, dict):
        return False
    command_rules = mapping.get("command_rules")
    if not isinstance(command_rules, list):
        return False
    for rule in command_rules:
        if not isinstance(rule, dict):
            continue
        command = rule.get("command")
        if isinstance(command, str) and command.strip():
            return True
    return False


def _command_rule_names(mapping: dict[str, Any] | None) -> set[str]:
    names: set[str] = set()
    if not isinstance(mapping, dict):
        return names
    command_rules = mapping.get("command_rules")
    if not isinstance(command_rules, list):
        return names
    for rule in command_rules:
        if not isinstance(rule, dict):
            continue
        command = rule.get("command")
        if not isinstance(command, str):
            continue
        cmd = command.strip()
        if not cmd or cmd.lower() == "void 0":
            continue
        names.add(cmd.upper())
    return names


def _is_action_command_name(command: str) -> bool:
    cmd = command.upper()
    return any(marker in cmd for marker in ("RESTART", "START", "STOP", "MODULE", "RESET", "REBOOT"))


def _is_menu_command_action(*, symbol: str, symbol_kinds: set[str], mapping: dict[str, Any] | None = None) -> bool:
    if "write" in symbol_kinds:
        return True
    return "special" in symbol_kinds and (_is_command_like_symbol(symbol) or _has_named_command_rule(mapping))


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
        kinds_raw = descriptor.get("menu_kinds")
        if isinstance(kinds_raw, list):
            menu_kinds = {str(kind).strip().lower() for kind in kinds_raw if isinstance(kind, str)}
        else:
            menu_kinds = set()
        writable = _is_menu_command_action(symbol=symbol, symbol_kinds=menu_kinds, mapping=mapping)

        if not _is_exposable_descriptor(writable=writable, pool=pool, chan=chan, idx=idx, mapping=mapping):
            continue

        enum_map, raw_to_label = _enum_maps(mapping, descriptor_unit=descriptor.get("unit"))
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
            unit=descriptor.get("unit"),
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
    per_module_symbol_kinds: dict[str, dict[str, set[str]]] = {}
    all_candidate_symbols: set[str] = set()

    for module in effective_modules:
        module_permissions = [str(perm) for perm in getattr(module, "permissions", []) or []]
        symbols: set[str] = set()
        panel_paths: dict[str, str] = {}

        try:
            groups = await resolver.build_panel_groups(
                device_menu=module.deviceMenu,
                permissions=module_permissions,
                all_panels=False,
            )
        except Exception:
            LOGGER.debug("Panel-group build failed for %s, retrying without permissions", module.devid, exc_info=True)
            groups = await resolver.build_panel_groups(
                device_menu=module.deviceMenu,
                permissions=None,
                all_panels=False,
            )

        symbols = {symbol for panel_symbols in groups.values() for symbol in panel_symbols if symbol}
        for panel_name, panel_symbols in groups.items():
            panel_title = _normalize_panel_path(str(panel_name))
            if not panel_title:
                continue
            for symbol in panel_symbols:
                if isinstance(symbol, str) and symbol and symbol not in panel_paths:
                    panel_paths[symbol] = panel_title

        per_module_candidate_symbols[module.devid] = symbols
        per_module_panel_paths[module.devid] = panel_paths
        per_module_symbol_kinds[module.devid] = {}
        assets = getattr(resolver, "_assets", None)
        if assets is not None and hasattr(assets, "get_module_menu"):
            try:
                menu = await assets.get_module_menu(device_menu=module.deviceMenu, permissions=module_permissions)
                per_module_symbol_kinds[module.devid] = _collect_symbol_kinds_from_menu(menu)
            except Exception:
                LOGGER.debug("Menu kind extraction failed for %s", module.devid, exc_info=True)
        if not per_module_symbol_kinds[module.devid] and assets is not None and hasattr(assets, "get_module_menu"):
            try:
                menu_all = await assets.get_module_menu(device_menu=module.deviceMenu, permissions=None)
                per_module_symbol_kinds[module.devid] = _collect_symbol_kinds_from_menu(menu_all)
            except Exception:
                LOGGER.debug("Menu kind fallback extraction failed for %s", module.devid, exc_info=True)
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
            symbol_kinds = per_module_symbol_kinds.get(module.devid, {}).get(symbol, set())
            mapping_raw = payload.get("mapping")
            mapping_dict = mapping_raw if isinstance(mapping_raw, dict) else None
            is_menu_write = _is_menu_command_action(symbol=symbol, symbol_kinds=symbol_kinds, mapping=mapping_dict)
            try:
                resolved = await resolver.resolve_value(symbol)
                keep_without_value = is_menu_write and (
                    _is_command_like_symbol(symbol) or _has_named_command_rule(mapping_dict)
                )
                if not keep_without_value and not _has_display_value(value=resolved.value, value_label=resolved.value_label):
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

        # Secondary pass: include command-like/special actions that are outside panel groups.
        extra_candidates = per_module_symbol_kinds.get(module.devid, {})
        symbols_to_resolve: list[str] = [
            symbol
            for symbol, kinds in extra_candidates.items()
            if symbol not in module_symbols and ("write" in kinds or "special" in kinds) and symbol not in details
        ]
        if symbols_to_resolve:
            try:
                extra_details = await resolver.describe_symbols(sorted(set(symbols_to_resolve)))
                details.update(extra_details)
            except Exception:
                LOGGER.debug(
                    "Extra descriptor batch resolution failed for %s (count=%s)",
                    module.devid,
                    len(symbols_to_resolve),
                    exc_info=True,
                )
        for symbol, kinds in extra_candidates.items():
            if symbol in module_symbols:
                continue
            if "write" not in kinds and "special" not in kinds:
                continue
            payload = details.get(symbol)
            if payload is None:
                if _is_command_like_symbol(symbol):
                    # Keep unresolved command-like tokens as synthetic button actions.
                    details[symbol] = {
                        "label": symbol,
                        "unit": None,
                        "pool": None,
                        "idx": None,
                        "chan": None,
                        "min": None,
                        "max": None,
                        "mapping": {
                            "command_rules": [{"command": symbol}],
                        },
                    }
                    payload = details[symbol]
                else:
                    continue
            mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else None
            if not _has_named_command_rule(mapping):
                continue
            commands = _command_rule_names(mapping)
            if _is_command_like_symbol(symbol) or any(_is_action_command_name(cmd) for cmd in commands):
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
            symbol_kinds = per_module_symbol_kinds.get(module.devid, {}).get(symbol, set())
            writable = _is_menu_command_action(symbol=symbol, symbol_kinds=symbol_kinds, mapping=mapping)
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
                "menu_kinds": sorted(symbol_kinds),
            }

            if not _is_exposable_descriptor(
                writable=writable,
                pool=descriptor.get("pool"),
                chan=descriptor.get("chan"),
                idx=descriptor.get("idx"),
                mapping=mapping,
            ):
                continue

            enum_map, raw_to_label = _enum_maps(mapping, descriptor_unit=payload.get("unit"))
            descriptor[CONF_OPTIONS] = _extract_options(mapping, descriptor_unit=payload.get("unit"))
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
                unit=payload.get("unit"),
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
