"""Runtime orchestration for the BragerOne HA integration."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from pybragerone import BragerOneApiClient, BragerOneGateway
from pybragerone.models.events import ParamUpdate
from pybragerone.models.param import ParamStore
from pybragerone.models.param_resolver import ParamResolver

from .command_write import WriteContext, WriteValidationError, prepare_write
from .numeric_display import descriptor_numeric_transform

UpdateCallback = Callable[[ParamUpdate], None]
# devid, online, online_changed — metadata-only updates set online_changed=False.
ConnectivityCallback = Callable[[str, bool, bool], None]
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BragerRuntime:
    """Holds live runtime objects and fan-outs updates to HA entities."""

    api: BragerOneApiClient
    gateway: BragerOneGateway
    store: ParamStore
    modules_meta: dict[str, dict[str, Any]]
    language: str | None = None

    _tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    _listeners: set[UpdateCallback] = field(default_factory=set)
    _connectivity_listeners: set[ConnectivityCallback] = field(default_factory=set)
    _module_online: dict[str, bool] = field(default_factory=dict)
    _start_monotonic: float | None = None
    _first_update_logged: bool = False
    _status_resolver: ParamResolver | None = None
    _resolver_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def start(self) -> None:
        """Start gateway, state store ingestion and update dispatcher."""
        self._start_monotonic = time.monotonic()
        self._first_update_logged = False
        self._tasks.append(asyncio.create_task(self.store.run_with_bus(self.gateway.bus), name="habragerone-store-sync"))
        self._tasks.append(asyncio.create_task(self._dispatch_updates(), name="habragerone-update-dispatch"))
        register = getattr(self.gateway, "on_module_connectivity", None)
        if self.supports_module_connectivity and callable(register):
            register(self._on_gateway_connectivity)
        try:
            await self.gateway.start()
        except Exception:
            for task in self._tasks:
                task.cancel()
            for task in self._tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._tasks.clear()
            raise
        self._seed_module_online_from_gateway()
        if self._start_monotonic is not None:
            LOGGER.debug(
                "Runtime gateway.start completed in %.3fs (modules=%s)",
                time.monotonic() - self._start_monotonic,
                len(self.gateway.modules),
            )

    async def stop(self) -> None:
        """Stop tasks and gateway resources."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._status_resolver = None
        await self.gateway.stop()
        await self.api.close()

    def add_listener(self, callback: UpdateCallback) -> Callable[[], None]:
        """Register an entity listener and return unsubscribe callable."""
        self._listeners.add(callback)

        def _remove() -> None:
            self._listeners.discard(callback)

        return _remove

    def add_connectivity_listener(self, callback: ConnectivityCallback) -> Callable[[], None]:
        """Register a module online/offline listener and return unsubscribe callable."""
        self._connectivity_listeners.add(callback)

        def _remove() -> None:
            self._connectivity_listeners.discard(callback)

        return _remove

    def module_online(self, devid: str) -> bool | None:
        """Return cached module online state, or ``None`` if not yet known."""
        return self._module_online.get(devid)

    @property
    def supports_module_connectivity(self) -> bool:
        """Return whether the gateway exposes the module connectivity API."""
        return callable(getattr(self.gateway, "on_module_connectivity", None)) and callable(
            getattr(self.gateway, "module_online", None)
        )

    def _seed_module_online_from_gateway(self) -> None:
        """Pull initial online bits from the gateway after start."""
        if not self.supports_module_connectivity:
            return
        modules = getattr(self.gateway, "modules", None)
        if not isinstance(modules, list):
            return
        online_getter = getattr(self.gateway, "module_online", None)
        connected_at_getter = getattr(self.gateway, "module_connected_at", None)
        gateway_getter = getattr(self.gateway, "module_gateway", None)
        if not callable(online_getter):
            return
        for raw_devid in modules:
            devid = str(raw_devid)
            online = online_getter(devid)
            if not isinstance(online, bool):
                continue
            connected_at = connected_at_getter(devid) if callable(connected_at_getter) else None
            gateway = gateway_getter(devid) if callable(gateway_getter) else None
            self._apply_module_online(
                devid,
                online,
                connected_at=connected_at if isinstance(connected_at, int) else None,
                gateway=gateway if isinstance(gateway, dict) else None,
                online_changed=True,
            )

    def _on_gateway_connectivity(self, event: Any) -> None:
        """Handle ``ModuleConnectivity`` (or duck-typed) events from the gateway."""
        devid = str(getattr(event, "devid", "") or "")
        online = getattr(event, "online", None)
        if not devid or not isinstance(online, bool):
            return
        connected_at = getattr(event, "connected_at", None)
        gateway = getattr(event, "gateway", None)
        online_changed = getattr(event, "online_changed", True)
        if not isinstance(online_changed, bool):
            online_changed = True
        self._apply_module_online(
            devid,
            online,
            connected_at=connected_at if isinstance(connected_at, int) else None,
            gateway=gateway if isinstance(gateway, dict) else None,
            online_changed=online_changed,
        )

    def _apply_module_online(
        self,
        devid: str,
        online: bool,
        *,
        connected_at: int | None,
        gateway: dict[str, Any] | None = None,
        online_changed: bool | None = None,
    ) -> None:
        """Update cache/modules_meta and notify connectivity listeners."""
        previous = self._module_online.get(devid)
        self._module_online[devid] = online
        meta = self.modules_meta.setdefault(devid, {})
        if connected_at is not None:
            meta["connectedAt"] = connected_at
        if gateway is not None:
            meta["gateway"] = dict(gateway)
        flipped = previous is not online if online_changed is None else online_changed
        for callback in list(self._connectivity_listeners):
            try:
                self._invoke_connectivity_listener(callback, devid, online, flipped)
            except Exception:
                LOGGER.exception("Connectivity listener failed for devid=%s", devid)

    @staticmethod
    def _invoke_connectivity_listener(
        callback: ConnectivityCallback,
        devid: str,
        online: bool,
        flipped: bool,
    ) -> None:
        """Call a connectivity listener with 2- or 3-arg compatibility.

        Signature inspection avoids treating a ``TypeError`` raised *inside* a
        modern 3-arg listener as an old 2-arg signature mismatch.
        """
        try:
            parameters = inspect.signature(callback).parameters.values()
        except TypeError, ValueError:
            callback(devid, online, flipped)
            return
        positional = [param for param in parameters if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)]
        accepts_varargs = any(param.kind == param.VAR_POSITIONAL for param in parameters)
        if accepts_varargs or len(positional) >= 3:
            callback(devid, online, flipped)
            return
        callback(devid, online)  # type: ignore[call-arg]

    async def async_write(
        self,
        *,
        descriptor: dict[str, Any],
        input_display_value: str | int | float | bool,
        enum_mapping: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        """Validate and dispatch command writes for any entity platform."""
        symbol = str(descriptor.get("symbol", ""))
        devid = str(descriptor.get("devid", ""))
        pool = descriptor.get("pool")
        chan = descriptor.get("chan")
        idx = descriptor.get("idx")
        mapping = descriptor.get("mapping") if isinstance(descriptor.get("mapping"), dict) else None
        command_rules = mapping.get("command_rules") if isinstance(mapping, dict) else None

        if not devid:
            raise HomeAssistantError(f"Missing device id for symbol '{symbol}'")

        if self.module_online(devid) is False:
            raise HomeAssistantError(f"Module '{devid}' is offline; refusing write for '{symbol}'")

        has_parameter_address = isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int)
        if isinstance(command_rules, list):
            typed_command_rules = [rule for rule in command_rules if isinstance(rule, dict)]
        else:
            typed_command_rules = []
        has_command_rule = len(typed_command_rules) > 0
        flat_values = self.store.flatten()
        default_actual: Any = None
        if isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int):
            default_actual = flat_values.get(f"{pool}.{chan}{idx}")
        active_rule = _select_active_command_rule(
            command_rules=typed_command_rules,
            flat_values=flat_values,
            devid=devid,
            modules_meta=self.modules_meta,
            default_actual=default_actual,
        )
        active_command = _rule_command_name(active_rule)
        has_raw_command_route = isinstance(active_command, str) and bool(active_command.strip())

        context = WriteContext(
            symbol=symbol,
            has_parameter_address=has_parameter_address,
            has_command_rule=has_command_rule,
            enum_mapping=enum_mapping,
            transform=descriptor_numeric_transform(descriptor),
            raw_min=descriptor.get("min") if isinstance(descriptor.get("min"), int | float) else None,
            raw_max=descriptor.get("max") if isinstance(descriptor.get("max"), int | float) else None,
        )
        try:
            prepared = prepare_write(input_display_value, context=context)
        except WriteValidationError as err:
            raise HomeAssistantError(str(err)) from err

        intent_rule = _select_intent_command_rule(command_rules=typed_command_rules, desired_value=prepared.raw_value)
        if _rule_command_name(intent_rule) is not None:
            active_rule = intent_rule
            active_command = _rule_command_name(active_rule)
            has_raw_command_route = isinstance(active_command, str) and bool(active_command.strip())

        if has_raw_command_route:
            raw_value = active_rule.get("value", prepared.raw_value)
            ok = await self.api.module_command_auto(
                devid=devid,
                command=str(active_command).strip(),
                value=raw_value,
            )
            if not ok:
                raise HomeAssistantError(f"Command write failed for '{symbol}' via raw command route")
            return

        if prepared.route == "parameter_write":
            parameter = f"{chan}{idx}"
            mapping_raw = descriptor.get("mapping")
            mapping_dict = mapping_raw if isinstance(mapping_raw, dict) else {}
            mapping_source = mapping_dict.get("raw")
            parameter_name = mapping_source.get("name") if isinstance(mapping_source, Mapping) else None
            parameter_name = parameter_name.strip() or None if isinstance(parameter_name, str) else None
            ok = await self.api.module_command_auto(
                devid=devid,
                pool=str(pool),
                parameter=parameter,
                value=prepared.raw_value,
                parameter_name=parameter_name,
            )
            if not ok:
                raise HomeAssistantError(f"Command write failed for '{symbol}' via parameter route")
            return

        rule = _select_command_rule(command_rules=typed_command_rules, desired_value=prepared.raw_value)
        command = _rule_command_name(rule)
        if command is None:
            raise HomeAssistantError(f"No raw command mapping available for '{symbol}'")
        raw_value = rule.get("value", prepared.raw_value)
        ok = await self.api.module_command_auto(
            devid=devid,
            command=command,
            value=raw_value,
        )
        if not ok:
            raise HomeAssistantError(f"Command write failed for '{symbol}' via raw command route")

    async def async_resolve_status_label(self, symbol: str) -> Any | None:
        """Resolve STATUS_* value exactly as parser/UI logic does."""
        if not symbol.startswith("STATUS_"):
            return None
        resolved = await self._async_resolve_symbol(symbol)
        if resolved is None:
            return None
        if isinstance(resolved.value_label, str) and resolved.value_label.strip():
            return resolved.value_label.strip()
        return resolved.value

    async def async_resolve_symbol_value(self, symbol: str) -> Any | None:
        """Resolve symbol value using parser rules and dynamic unit transforms."""
        resolved = await self._async_resolve_symbol(symbol)
        if resolved is None:
            return None
        if isinstance(resolved.value_label, str) and resolved.value_label.strip():
            return resolved.value_label.strip()
        return resolved.value

    async def async_resolve_symbol_with_unit(self, symbol: str) -> tuple[Any | None, Any | None]:
        """Resolve symbol value and unit using parser rules."""
        resolved = await self._async_resolve_symbol(symbol)
        if resolved is None:
            return None, None
        value: Any = (
            resolved.value_label if isinstance(resolved.value_label, str) and resolved.value_label.strip() else resolved.value
        )
        return value, resolved.unit

    async def _async_resolve_symbol(self, symbol: str) -> Any | None:
        resolver = await self._async_get_resolver()
        if resolver is None:
            return None
        try:
            return await resolver.resolve_value(symbol)
        except Exception:
            return None

    async def _async_get_resolver(self) -> ParamResolver | None:
        if self._status_resolver is not None:
            return self._status_resolver
        async with self._resolver_lock:
            try:
                self._status_resolver = ParamResolver.from_api(
                    api=self.api,
                    store=self.store,
                    lang=self.language,
                )
            except Exception:
                return None
            return self._status_resolver

    async def _dispatch_updates(self) -> None:
        async for update in self.gateway.bus.subscribe():
            if not self._first_update_logged and self._start_monotonic is not None:
                source = update.meta.get("_source") if isinstance(update.meta, dict) else None
                LOGGER.debug(
                    "First runtime update after %.3fs (source=%s, devid=%s, key=%s.%s%s)",
                    time.monotonic() - self._start_monotonic,
                    source,
                    update.devid,
                    update.pool,
                    update.chan,
                    update.idx,
                )
                self._first_update_logged = True
            for callback in tuple(self._listeners):
                try:
                    callback(update)
                except Exception:
                    LOGGER.exception("Runtime listener callback failed for update %s.%s%s", update.pool, update.chan, update.idx)


def _select_command_rule(*, command_rules: list[dict[str, Any]], desired_value: Any) -> dict[str, Any]:
    desired_normalized = str(desired_value).strip().lower()
    for rule in command_rules:
        logic = str(rule.get("logic", "")).strip().lower()
        if isinstance(desired_value, bool) and ((desired_value and logic == "on") or ((not desired_value) and logic == "off")):
            return rule

        rule_value = rule.get("value")
        if str(rule_value).strip().lower() == desired_normalized:
            return rule

    for rule in command_rules:
        if _rule_command_name(rule) is not None:
            return rule
    return {}


def _rule_command_name(rule: Mapping[str, Any]) -> str | None:
    command_raw = rule.get("command")
    if not isinstance(command_raw, str):
        return None
    command = command_raw.strip()
    if not command or command.lower() == "void 0":
        return None
    return command


def _select_intent_command_rule(*, command_rules: list[dict[str, Any]], desired_value: Any) -> dict[str, Any]:
    if not isinstance(desired_value, bool):
        return {}

    # Prefer explicit logic tags when available.
    desired_logic = "on" if desired_value else "off"
    for rule in command_rules:
        logic = str(rule.get("logic", "")).strip().lower()
        if logic == desired_logic and _rule_command_name(rule) is not None:
            return rule

    # Fallback for symbolic command names like BOILER_START/BOILER_STOP.
    for rule in command_rules:
        command = _rule_command_name(rule)
        if command is None:
            continue
        cmd = command.strip().upper()
        if desired_value and ("START" in cmd or "ENABLE" in cmd or cmd.endswith("_ON")):
            return rule
        if (not desired_value) and ("STOP" in cmd or "DISABLE" in cmd or cmd.endswith("_OFF")):
            return rule

    return {}


def _select_active_command_rule(
    *,
    command_rules: list[dict[str, Any]],
    flat_values: Mapping[str, Any],
    devid: str,
    modules_meta: Mapping[str, Mapping[str, Any]],
    default_actual: Any,
) -> dict[str, Any]:
    for rule in command_rules:
        if _command_rule_matches(
            rule,
            flat_values=flat_values,
            devid=devid,
            modules_meta=modules_meta,
            default_actual=default_actual,
        ):
            return rule
    for rule in command_rules:
        if _rule_command_name(rule) is not None:
            return rule
    return {}


def _command_rule_matches(
    rule: Mapping[str, Any],
    *,
    flat_values: Mapping[str, Any],
    devid: str,
    modules_meta: Mapping[str, Mapping[str, Any]],
    default_actual: Any,
) -> bool:
    conditions = rule.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        return True

    for cond in conditions:
        if not isinstance(cond, Mapping):
            return False
        operation = cond.get("operation")
        expected = cond.get("expected")
        targets = cond.get("targets")
        if not isinstance(operation, str):
            return False
        if not isinstance(targets, list) or not targets:
            return _compare_condition(operation=operation, actual=default_actual, expected=expected)
        for target in targets:
            if not isinstance(target, Mapping):
                return False
            actual = _read_target_actual(target, flat_values=flat_values, devid=devid, modules_meta=modules_meta)
            if not _compare_condition(operation=operation, actual=actual, expected=expected):
                return False
    return True


def _read_target_actual(
    target: Mapping[str, Any],
    *,
    flat_values: Mapping[str, Any],
    devid: str,
    modules_meta: Mapping[str, Mapping[str, Any]],
) -> Any:
    address = target.get("address")
    if isinstance(address, str) and address.strip():
        value = flat_values.get(address.strip())
    else:
        group = target.get("group")
        use = target.get("use")
        number = target.get("number")
        key = f"{group}.{use}{number}" if isinstance(group, str) and isinstance(use, str) and isinstance(number, int) else None
        value = flat_values.get(key) if isinstance(key, str) else None

    if value is None:
        getter = target.get("storeGetter")
        if isinstance(getter, str) and getter.endswith("connectedAt"):
            value = modules_meta.get(devid, {}).get("connectedAt")

    bit = target.get("bit")
    if isinstance(bit, int):
        bitmask_value: int | None = None
        if isinstance(value, bool):
            bitmask_value = None
        elif isinstance(value, int):
            bitmask_value = value
        elif isinstance(value, float) and value.is_integer():
            bitmask_value = int(value)
        if bitmask_value is not None:
            return (bitmask_value >> bit) & 1
    return value


def _compare_condition(*, operation: str, actual: Any, expected: Any) -> bool:
    op = operation.strip()
    if "." in op:
        op = op.rsplit(".", 1)[-1]
    if op == "equalTo":
        return bool(actual == expected)
    if op == "notEqualTo":
        return bool(actual != expected)
    return False
