"""Bootstrap helpers for one-time metadata extraction and caching."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, TypedDict, cast

from .const import (
    CONF_BOOTSTRAP_DEBUG,
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
_BINARY_UNITS_SOURCE_CODES = {9994, 9995, 9996}
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


def _is_binary_status_rule(mapping: dict[str, Any] | None) -> bool:
    if not isinstance(mapping, dict):
        return False
    command_rules = mapping.get("command_rules")
    if not isinstance(command_rules, list) or not command_rules:
        return False
    values: set[str] = set()
    for candidate in command_rules:
        if not isinstance(candidate, dict):
            continue
        value = candidate.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        token = value.strip().lower()
        if "." in token:
            token = token.rsplit(".", 1)[-1]
        values.add(token)
    if not values:
        return False
    return values.issubset({"on", "off", "on_manual", "off_manual", "enabled", "disabled"})


def _binary_key(value: Any) -> int | None:
    raw = _coerce_raw(value)
    if isinstance(raw, bool):
        return 1 if raw else 0
    if isinstance(raw, int):
        if raw in (0, 1):
            return raw
        return None
    if isinstance(raw, str):
        norm = raw.strip().casefold()
        if norm in {"0", "false", "off", "disabled", "no"}:
            return 0
        if norm in {"1", "true", "on", "enabled", "yes"}:
            return 1
    return None


def _is_binary_status_unit(unit: Any) -> bool:
    if not isinstance(unit, Mapping) or len(unit) != 2:
        return False
    keys: set[int] = set()
    for raw_key in unit:
        parsed = _binary_key(raw_key)
        if parsed is None:
            return False
        keys.add(parsed)
    return keys == {0, 1}


def _is_binary_units_source(mapping: dict[str, Any] | None) -> bool:
    if not isinstance(mapping, dict):
        return False
    units_source = mapping.get("units_source")
    code: int | None = None
    if isinstance(units_source, int):
        code = units_source
    elif isinstance(units_source, str):
        text = units_source.strip()
        if text.startswith("wn."):
            text = text[3:]
        if text.isdigit():
            code = int(text)
    return code in _BINARY_UNITS_SOURCE_CODES


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

    if not writable and _is_binary_status_unit(unit):
        return "binary_sensor"

    if (chan == "s" or symbol_norm.startswith("STATUS_") or "status" in component_type) and not writable:
        if _is_binary_status_rule(mapping):
            return "binary_sensor"
        if _is_binary_units_source(mapping):
            return "binary_sensor"
        values = mapping.get("values") if isinstance(mapping, dict) else None
        units_source = mapping.get("units_source") if isinstance(mapping, dict) else None
        command_rules = mapping.get("command_rules") if isinstance(mapping, dict) else None
        if isinstance(unit, Mapping) and unit:
            return "sensor"
        if isinstance(values, list) and values:
            return "sensor"
        if units_source not in (None, "", 0):
            return "sensor"
        if isinstance(command_rules, list) and command_rules:
            return "sensor"
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

    if isinstance(values, list) and values:
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


def _collect_symbol_route_meta_from_menu(menu: Any) -> dict[str, list[dict[str, Any]]]:
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    stack = list(_get_field(menu, "routes") or [])[::-1]
    while stack:
        route = stack.pop()
        symbols = _collect_symbols_from_route(route)
        route_meta = _get_field(route, "meta")
        route_name = _get_field(route, "name")
        route_path = _get_field(route, "path")
        route_display = _get_field(route_meta, "displayName") if route_meta is not None else None
        route_visible = _get_field(route_meta, "isVisibleOnSideMenu") if route_meta is not None else None
        route_dropdown = _get_field(route_meta, "displayDropdown") if route_meta is not None else None
        route_component = _get_field(route, "component")
        payload = {
            "name": route_name,
            "path": route_path,
            "display_name": route_display,
            "is_visible_on_side_menu": route_visible,
            "display_dropdown": route_dropdown,
            "component": str(route_component) if route_component is not None else None,
        }
        for symbol in symbols:
            symbol_routes.setdefault(symbol, []).append(payload)
        children = _get_field(route, "children")
        if isinstance(children, list):
            for child in reversed(children):
                stack.append(child)
    return symbol_routes


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


def _has_runtime_raw_value(
    *,
    payload: Mapping[str, Any],
    mapping: Mapping[str, Any] | None,
    flat_values: Mapping[str, Any],
) -> bool:
    pool = payload.get("pool")
    chan = payload.get("chan")
    idx = payload.get("idx")
    if isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int):
        direct_key = f"{pool}.{chan}{idx}"
        if flat_values.get(direct_key) is not None:
            return True
    if not isinstance(mapping, Mapping):
        return False
    inputs = mapping.get("inputs")
    if not isinstance(inputs, list):
        return False
    for candidate in inputs:
        if not isinstance(candidate, Mapping):
            continue
        address = candidate.get("address")
        if not isinstance(address, str) or not address.strip():
            continue
        if flat_values.get(address.strip()) is not None:
            return True
    return False


def _is_boiler_panel(panel_path: str) -> bool:
    return _normalize_panel_path(panel_path) == "Kocioł"


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


def _mapping_has_parameter_write(mapping: dict[str, Any] | None) -> bool:
    """Return whether the ParamMap declares a write to a value channel.

    Live menus sometimes list editable PARAMs only under ``status`` (or omit
    kinds entirely for panel-only candidates). Those still carry
    ``paths.command`` entries such as ``{group: P6, number: 61, use: v}``.
    """
    if not isinstance(mapping, dict):
        return False
    paths = mapping.get("paths")
    if not isinstance(paths, Mapping):
        return False
    commands = paths.get("command")
    if not isinstance(commands, list):
        return False
    for entry in commands:
        if not isinstance(entry, Mapping):
            continue
        group = entry.get("group") if entry.get("group") is not None else entry.get("pool")
        number = entry.get("number")
        if number is None:
            number = entry.get("index")
        if number is None:
            number = entry.get("idx")
        use = entry.get("use")
        if use is None:
            use = entry.get("path")
        if use is None:
            use = entry.get("pathType")
        if use is None:
            use = entry.get("chan")
        if not isinstance(group, str) or not group.strip():
            continue
        if not isinstance(number, int):
            continue
        if not isinstance(use, str) or not use.strip():
            continue
        use_norm = use.strip().lower()
        if use_norm in {"v", "value"}:
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
    if "special" in symbol_kinds and (_is_command_like_symbol(symbol) or _has_named_command_rule(mapping)):
        return True
    # STATUS_* computed rules must stay read-only even when they expose command_rules.
    if symbol.upper().startswith("STATUS_"):
        return False
    return _mapping_has_parameter_write(mapping)


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


def _panel_group_symbols(groups: Mapping[str, list[str]]) -> set[str]:
    """Flatten a panel-group mapping into the set of symbols it contains.

    Args:
        groups: Mapping of panel name to the symbols assigned to that panel.

    Returns:
        Set of non-empty symbols found across every panel.
    """
    return {symbol for panel_symbols in groups.values() for symbol in panel_symbols if symbol}


async def _build_panel_groups_with_fallback(
    resolver: Any,
    *,
    device_menu: Any,
    permissions: list[str],
    devid: str,
    web_ui_only: bool = False,
) -> dict[str, list[str]]:
    """Build panel groups, retrying without permissions when the gated attempt yields nothing.

    The permission-gated extraction can fail in two ways: it can raise, or it can succeed and
    still return no symbols. Both are treated the same way and retried with ``permissions=None``,
    mirroring the symbol-kind fallback used later in the same bootstrap loop.

    A failing ungated retry is left to propagate, as it did before the empty-result case was
    handled here. Setup then fails and Home Assistant retries it, which is recoverable; swallowing
    the error would instead hand back an empty result as if the extraction had succeeded.

    Args:
        resolver: Parameter resolver used for the extraction.
        device_menu: Device menu identifier of the module.
        permissions: Permission strings reported by the API for this module.
        devid: Module device identifier, used for logging only.
        web_ui_only: When True, exclude installer/service routes (everyday web-UI panels only).

    Returns:
        Mapping of panel name to symbols, empty when neither attempt produced symbols.
    """
    groups: dict[str, list[str]] = {}
    try:
        groups = await resolver.build_panel_groups(
            device_menu=device_menu,
            permissions=permissions,
            all_panels=True,
            web_ui_only=web_ui_only,
        )
    except Exception:
        LOGGER.debug("Panel-group build failed for %s, retrying without permissions", devid, exc_info=True)
    else:
        if _panel_group_symbols(groups):
            return groups
        LOGGER.debug("Panel-group build returned no symbols for %s, retrying without permissions", devid)

    groups = await resolver.build_panel_groups(
        device_menu=device_menu,
        permissions=None,
        all_panels=True,
        web_ui_only=web_ui_only,
    )

    if not _panel_group_symbols(groups):
        # Scope the claim to panel-derived symbols: in permissions mode the later secondary pass
        # can still contribute command-like entities that never came from a panel group.
        LOGGER.warning(
            "Panel-group discovery returned no symbols for module %s, with and without permissions; "
            "no panel-derived entities will be created for it",
            devid,
        )
    return groups


class BootstrapPayload(TypedDict):
    """Container persisted in ConfigEntry data for fast startup."""

    entity_descriptors: list[EntityDescriptor]
    modules_meta: dict[str, dict[str, Any]]
    entity_filter_mode: str
    module_filter_modes: dict[str, str]
    bootstrap_debug: dict[str, Any]


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
    per_module_symbol_routes: dict[str, dict[str, list[dict[str, Any]]]] = {}
    per_module_route_diagnostics: dict[str, list[dict[str, Any]]] = {}
    all_candidate_symbols: set[str] = set()
    bootstrap_debug: dict[str, Any] = {"modules": {}, "limits": {"max_rejections_per_module": 500}}

    for module in effective_modules:
        module_permissions = [str(perm) for perm in getattr(module, "permissions", []) or []]
        symbols: set[str] = set()
        panel_paths: dict[str, str] = {}
        module_mode = normalized_module_modes.get(str(module.devid), filter_mode)
        web_ui_only = module_mode == FILTER_MODE_UI

        groups = await _build_panel_groups_with_fallback(
            resolver,
            device_menu=module.deviceMenu,
            permissions=module_permissions,
            devid=str(module.devid),
            web_ui_only=web_ui_only,
        )

        symbols = _panel_group_symbols(groups)
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
        per_module_symbol_routes[module.devid] = {}
        per_module_route_diagnostics[module.devid] = []
        assets = getattr(resolver, "_assets", None)
        if assets is not None and hasattr(assets, "get_module_menu"):
            try:
                menu = await assets.get_module_menu(device_menu=module.deviceMenu, permissions=module_permissions)
                per_module_symbol_kinds[module.devid] = _collect_symbol_kinds_from_menu(menu)
                per_module_symbol_routes[module.devid] = _collect_symbol_route_meta_from_menu(menu)
                per_module_route_diagnostics[module.devid] = resolver.panel_route_diagnostics_from_menu(
                    menu,
                    all_panels=True,
                    web_ui_only=web_ui_only,
                    routes_i18n=await resolver._i18n.get_namespace("routes"),
                )
            except Exception:
                LOGGER.debug("Menu kind extraction failed for %s", module.devid, exc_info=True)
        if not per_module_symbol_kinds[module.devid] and assets is not None and hasattr(assets, "get_module_menu"):
            try:
                menu_all = await assets.get_module_menu(device_menu=module.deviceMenu, permissions=None)
                per_module_symbol_kinds[module.devid] = _collect_symbol_kinds_from_menu(menu_all)
                per_module_symbol_routes[module.devid] = _collect_symbol_route_meta_from_menu(menu_all)
                per_module_route_diagnostics[module.devid] = resolver.panel_route_diagnostics_from_menu(
                    menu_all,
                    all_panels=True,
                    web_ui_only=web_ui_only,
                    routes_i18n=await resolver._i18n.get_namespace("routes"),
                )
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
        module_rejections: list[dict[str, Any]] = []
        module_accepts: list[dict[str, Any]] = []
        boiler_accepts: list[dict[str, Any]] = []
        module_candidates = per_module_candidate_symbols.get(module.devid, set())
        kinds_map = per_module_symbol_kinds.get(module.devid, {})
        routes_map = per_module_symbol_routes.get(module.devid, {})
        kinds_symbols = set(kinds_map.keys())
        not_in_candidates = sorted(kinds_symbols - module_candidates)
        bootstrap_debug["modules"][module.devid] = {
            "candidate_count": len(module_candidates),
            "candidate_symbols_sample": sorted(module_candidates)[:200],
            "menu_symbol_kinds_count": len(kinds_symbols),
            "menu_symbols_not_in_candidates_count": len(not_in_candidates),
            "menu_symbols_not_in_candidates_sample": not_in_candidates[:200],
            "menu_symbol_routes_sample": {symbol: routes_map.get(symbol, [])[:5] for symbol in not_in_candidates[:50]},
            "accepted_count": 0,
            "rejection_count": 0,
            "rejections": module_rejections,
            "accepted_debug": module_accepts,
            "boiler_panel_debug": boiler_accepts,
            "route_diagnostics_summary": {
                "accepted": sum(1 for row in per_module_route_diagnostics.get(module.devid, []) if bool(row.get("accepted"))),
                "rejected": sum(1 for row in per_module_route_diagnostics.get(module.devid, []) if not bool(row.get("accepted"))),
            },
            "route_diagnostics_sample": per_module_route_diagnostics.get(module.devid, [])[:300],
        }
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

        for symbol in module_candidates:
            payload = details.get(symbol)
            if payload is None:
                if len(module_rejections) < 500:
                    module_rejections.append({"symbol": symbol, "reason": "missing_descriptor"})
                continue
            symbol_kinds = per_module_symbol_kinds.get(module.devid, {}).get(symbol, set())
            mapping_raw = payload.get("mapping")
            mapping_dict = mapping_raw if isinstance(mapping_raw, dict) else None
            is_menu_write = _is_menu_command_action(symbol=symbol, symbol_kinds=symbol_kinds, mapping=mapping_dict)
            panel_path = per_module_panel_paths.get(module.devid, {}).get(symbol, "")
            resolved_value: Any = None
            resolved_value_label: Any = None
            keep_without_value = False
            has_runtime_raw = False
            visible_diag: Any = None
            try:
                resolved = await resolver.resolve_value(symbol)
                resolved_value = resolved.value
                resolved_value_label = resolved.value_label
                keep_without_value = is_menu_write and (_is_command_like_symbol(symbol) or _has_named_command_rule(mapping_dict))
                if not keep_without_value and not _has_display_value(value=resolved.value, value_label=resolved.value_label):
                    if len(module_rejections) < 500:
                        module_rejections.append(
                            {
                                "symbol": symbol,
                                "reason": "no_display_value",
                                "value": resolved_value,
                                "value_label": resolved_value_label,
                                "menu_kinds": sorted(symbol_kinds),
                            }
                        )
                    continue
                has_runtime_raw = _has_runtime_raw_value(payload=payload, mapping=mapping_dict, flat_values=flat_values)

                if module_mode == FILTER_MODE_UI:
                    visible, visible_diag = resolver.parameter_visibility_diagnostics(
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
                if len(module_accepts) < 500:
                    module_accepts.append(
                        {
                            "symbol": symbol,
                            "panel_path": panel_path,
                            "menu_kinds": sorted(symbol_kinds),
                            "keep_without_value": keep_without_value,
                            "has_runtime_raw": has_runtime_raw,
                            "value": resolved_value,
                            "value_label": resolved_value_label,
                            "ui_visible_diag": visible_diag,
                        }
                    )
                if _is_boiler_panel(panel_path) and len(boiler_accepts) < 200:
                    boiler_accepts.append(
                        {
                            "symbol": symbol,
                            "menu_kinds": sorted(symbol_kinds),
                            "keep_without_value": keep_without_value,
                            "has_runtime_raw": has_runtime_raw,
                            "value": resolved_value,
                            "value_label": resolved_value_label,
                            "ui_visible_diag": visible_diag,
                        }
                    )
            else:
                if len(module_rejections) < 500:
                    module_rejections.append(
                        {
                            "symbol": symbol,
                            "reason": "ui_visibility_false",
                            "menu_kinds": sorted(symbol_kinds),
                            "value": resolved_value,
                            "value_label": resolved_value_label,
                            "ui_visible_diag": visible_diag,
                        }
                    )

        # Secondary pass: include command-like/special actions that are outside panel groups.
        # In UI mode keep parity with CLI and expose only panel-derived symbols.
        if module_mode != FILTER_MODE_UI:
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
        module_debug = bootstrap_debug["modules"].get(module.devid)
        if isinstance(module_debug, dict):
            module_debug["accepted_count"] = len(module_symbols)
            module_debug["rejection_count"] = len(module_rejections)
            accepted_symbols_sample = sorted(module_symbols)[:200]
            module_debug["accepted_symbols_sample"] = accepted_symbols_sample
            module_debug["accepted_symbol_routes_sample"] = {
                symbol: routes_map.get(symbol, [])[:5] for symbol in accepted_symbols_sample
            }

    resolver.set_runtime_context(None)

    descriptors: list[EntityDescriptor] = []
    modules_meta: dict[str, dict[str, Any]] = {}

    for module in effective_modules:
        module_mode = normalized_module_modes.get(str(module.devid), filter_mode)
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
            panel_path = per_module_panel_paths.get(module.devid, {}).get(symbol, "")
            unit_value = payload.get("unit")
            if unit_value is None and isinstance(mapping, dict):
                unit_candidates: list[Any] = []
                units_source = mapping.get("units_source")
                if isinstance(units_source, (int, float, str)) and str(units_source).strip():
                    unit_candidates.append(units_source)
                    if isinstance(units_source, int):
                        unit_candidates.append(str(units_source))
                        unit_candidates.append(f"wn.{units_source}")
                raw_mapping = mapping.get("raw")
                if isinstance(raw_mapping, dict):
                    raw_units = raw_mapping.get("units")
                    if raw_units not in (None, "", 0):
                        unit_candidates.append(raw_units)
                    raw_unit = raw_mapping.get("unit")
                    if raw_unit not in (None, "", 0):
                        unit_candidates.append(raw_unit)
                seen_candidates: set[str] = set()
                for candidate in unit_candidates:
                    key = str(candidate)
                    if key in seen_candidates:
                        continue
                    seen_candidates.add(key)
                    with suppress(Exception):
                        resolved_unit = await resolver.resolve_unit(candidate)
                        if resolved_unit is not None:
                            unit_value = resolved_unit
                            break

            descriptor: EntityDescriptor = {
                "key": f"{module.devid}:{symbol}",
                "symbol": symbol,
                "devid": module.devid,
                "module_name": module.name,
                "module_title": module.moduleTitle,
                "module_version": module.moduleVersion,
                "device_menu": module.deviceMenu,
                "panel_path": panel_path,
                "label": label,
                "unit": unit_value,
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

            enum_map, raw_to_label = _enum_maps(mapping, descriptor_unit=unit_value)
            descriptor[CONF_OPTIONS] = _extract_options(mapping, descriptor_unit=unit_value)
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
                unit=unit_value,
            )
            descriptors.append(descriptor)

    return {
        CONF_ENTITY_DESCRIPTORS: descriptors,
        CONF_MODULES_META: modules_meta,
        CONF_ENTITY_FILTER_MODE: filter_mode,
        CONF_MODULE_FILTER_MODES: {
            str(module.devid): normalized_module_modes.get(str(module.devid), filter_mode) for module in effective_modules
        },
        CONF_BOOTSTRAP_DEBUG: bootstrap_debug,
    }
