"""Runtime orchestration for the BragerOne HA integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from pybragerone import BragerOneApiClient, BragerOneGateway
from pybragerone.models.events import ParamUpdate
from pybragerone.models.param import ParamStore

from .command_write import WriteContext, WriteValidationError, prepare_write

UpdateCallback = Callable[[ParamUpdate], None]
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BragerRuntime:
    """Holds live runtime objects and fan-outs updates to HA entities."""

    api: BragerOneApiClient
    gateway: BragerOneGateway
    store: ParamStore
    modules_meta: dict[str, dict[str, Any]]

    _tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    _listeners: set[UpdateCallback] = field(default_factory=set)
    _start_monotonic: float | None = None
    _first_update_logged: bool = False

    async def start(self) -> None:
        """Start gateway, state store ingestion and update dispatcher."""
        self._start_monotonic = time.monotonic()
        self._first_update_logged = False
        self._tasks.append(asyncio.create_task(self.store.run_with_bus(self.gateway.bus), name="habragerone-store-sync"))
        self._tasks.append(asyncio.create_task(self._dispatch_updates(), name="habragerone-update-dispatch"))
        await self.gateway.start()
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
        await self.gateway.stop()
        await self.api.close()

    def add_listener(self, callback: UpdateCallback) -> Callable[[], None]:
        """Register an entity listener and return unsubscribe callable."""
        self._listeners.add(callback)

        def _remove() -> None:
            self._listeners.discard(callback)

        return _remove

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

        has_parameter_address = isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int)
        has_command_rule = isinstance(command_rules, list) and len(command_rules) > 0

        context = WriteContext(
            symbol=symbol,
            has_parameter_address=has_parameter_address,
            has_command_rule=has_command_rule,
            enum_mapping=enum_mapping,
            raw_min=descriptor.get("min") if isinstance(descriptor.get("min"), int | float) else None,
            raw_max=descriptor.get("max") if isinstance(descriptor.get("max"), int | float) else None,
        )
        try:
            prepared = prepare_write(input_display_value, context=context)
        except WriteValidationError as err:
            raise HomeAssistantError(str(err)) from err

        if prepared.route == "parameter_write":
            parameter = f"{chan}{idx}"
            ok = await self.api.module_command_auto(
                devid=devid,
                pool=str(pool),
                parameter=parameter,
                value=prepared.raw_value,
            )
            if not ok:
                raise HomeAssistantError(f"Command write failed for '{symbol}' via parameter route")
            return

        rule = _select_command_rule(
            command_rules=[rule for rule in command_rules if isinstance(rule, dict)] if isinstance(command_rules, list) else [],
            desired_value=prepared.raw_value,
        )
        command = rule.get("command") if isinstance(rule.get("command"), str) else None
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
                callback(update)


def _select_command_rule(*, command_rules: list[dict[str, Any]], desired_value: Any) -> dict[str, Any]:
    desired_normalized = str(desired_value).strip().lower()
    for rule in command_rules:
        logic = str(rule.get("logic", "")).strip().lower()
        if isinstance(desired_value, bool) and ((desired_value and logic == "on") or ((not desired_value) and logic == "off")):
            return rule

        rule_value = rule.get("value")
        if str(rule_value).strip().lower() == desired_normalized:
            return rule

    return command_rules[0] if command_rules else {}
