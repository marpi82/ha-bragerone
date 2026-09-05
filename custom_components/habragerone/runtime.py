"""Runtime orchestration for the BragerOne HA integration."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from pybragerone import BragerOneApiClient, BragerOneGateway
from pybragerone.models.events import ParamUpdate
from pybragerone.models.param import ParamStore
from pybragerone.models.param_resolver import ParamResolver

from .command_write import WriteContext, WriteValidationError, prepare_write
from .const import CONF_ROUTE_VISIBILITY_DEPS, CONF_ROUTE_VISIBILITY_NAME, CONF_ROUTE_VISIBILITY_PATH, CONF_UI_ROUTE_SYMBOL
from .numeric_display import descriptor_numeric_transform
from .outage_attrs import (
    extract_live_push_fields,
    extract_outage_fields,
    live_push_snapshot_has_values,
    outage_snapshot_has_values,
)


def _import_alarm_name_helpers() -> tuple[Any, Any]:
    """Import AlarmName helpers; return ``(None, None)`` when unavailable.

    Runs at module load (and in unit tests) so async alarm refresh never calls
    ``importlib.import_module`` on the event loop.
    """
    try:
        from pybragerone.models.alarm_names import parse_alarm_name_enum, resolve_alarm_label
    except ImportError:  # Older py-bragerone wheels omit AlarmName helpers.
        return None, None
    return parse_alarm_name_enum, resolve_alarm_label


_parse_alarm_name_enum, _resolve_alarm_label = _import_alarm_name_helpers()

UpdateCallback = Callable[[ParamUpdate], None]
# devid, online, online_changed — metadata-only updates set online_changed=False.
ConnectivityCallback = Callable[[str, bool, bool], None]
# library↔cloud Socket.IO session: up, changed.
CloudSessionCallback = Callable[[bool, bool], None]
# live ParamUpdate push health flipped (or resume notify).
LivePushCallback = Callable[[], None]
# Module event-feed (alarms / activity) refresh completed for one devid.
EventFeedCallback = Callable[[str], None]
# Route visibility changed for one symbol on a module (devid, symbol, visible).
RouteVisibilityCallback = Callable[[str, str, bool], None]
LOGGER = logging.getLogger(__name__)

_ALARM_CHROME_KEYS = ("currentAlarms", "historyAlarms")
_ACTIVITY_PAGE = 1
_ACTIVITY_LIMIT = 20
_ALARMS_PAGE = 1
_ALARMS_LIMIT = 20


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
    _cloud_session_listeners: set[CloudSessionCallback] = field(default_factory=set)
    _live_push_listeners: set[LivePushCallback] = field(default_factory=set)
    _event_feed_listeners: set[EventFeedCallback] = field(default_factory=set)
    _module_online: dict[str, bool] = field(default_factory=dict)
    _cloud_session_up: bool | None = None
    _cloud_session_outage: dict[str, float | str | None] = field(default_factory=dict)
    _live_push_health: dict[str, float | bool | None] = field(default_factory=dict)
    _module_outage: dict[str, dict[str, float | str | None]] = field(default_factory=dict)
    _start_monotonic: float | None = None
    _first_update_logged: bool = False
    _status_resolver: ParamResolver | None = None
    _resolver_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _status_label_cache: dict[str, Any] = field(default_factory=dict)
    _alarms_current: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _alarms_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _alarm_chrome_labels: dict[str, str] | None = None
    _alarm_names: dict[int, str] = field(default_factory=dict)
    _errors_i18n: dict[str, Any] = field(default_factory=dict)
    _alarm_assets_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _alarm_names_loaded: bool = False
    _alarms_refresh_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    _alarms_feed_loaded: dict[str, bool] = field(default_factory=dict)
    _activity: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _activity_index_label: str | None = None
    _activity_state_i18n: dict[str, str] = field(default_factory=dict)
    _activity_assets_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _activity_assets_loaded: bool = False
    _activity_refresh_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    _activity_feed_loaded: dict[str, bool] = field(default_factory=dict)
    _background_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    _route_visibility_listeners: set[RouteVisibilityCallback] = field(default_factory=set)
    _symbol_route_visible: dict[str, bool] = field(default_factory=dict)
    _symbol_route_lookup: dict[str, tuple[str, str, str, str]] = field(default_factory=dict)
    _route_visibility_dep_to_symbols: dict[str, set[str]] = field(default_factory=dict)
    _menu_cache: dict[str, Any] = field(default_factory=dict)

    async def start(self) -> None:
        """Start gateway, state store ingestion and update dispatcher."""
        self._start_monotonic = time.monotonic()
        self._first_update_logged = False
        self._tasks.append(asyncio.create_task(self.store.run_with_bus(self.gateway.bus), name="habragerone-store-sync"))
        self._tasks.append(asyncio.create_task(self._dispatch_updates(), name="habragerone-update-dispatch"))
        register = getattr(self.gateway, "on_module_connectivity", None)
        if self.supports_module_connectivity and callable(register):
            register(self._on_gateway_connectivity)
        register_session = getattr(self.gateway, "on_cloud_session", None)
        if self.supports_cloud_session and callable(register_session):
            register_session(self._on_gateway_cloud_session)
        register_live_push = getattr(self.gateway, "on_live_push", None)
        if self.supports_live_push and callable(register_live_push):
            register_live_push(self._on_gateway_live_push)
        register_alarm_qty = getattr(self.gateway, "on_alarm_quantity", None)
        if self.supports_alarm_quantity and callable(register_alarm_qty):
            register_alarm_qty(self._on_gateway_alarm_quantity)
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
        self._seed_cloud_session_from_gateway()
        self._seed_live_push_from_gateway()
        await self.refresh_route_visibility()
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
        for task in list(self._background_tasks):
            task.cancel()
        for task in list(self._background_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._background_tasks.clear()
        for task in list(self._alarms_refresh_tasks.values()):
            task.cancel()
        for task in list(self._alarms_refresh_tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._alarms_refresh_tasks.clear()
        for task in list(self._activity_refresh_tasks.values()):
            task.cancel()
        for task in list(self._activity_refresh_tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._activity_refresh_tasks.clear()
        self._status_resolver = None
        await self.gateway.stop()
        await self.api.close()

    def add_route_visibility_listener(self, callback: RouteVisibilityCallback) -> Callable[[], None]:
        """Register a route-visibility listener and return unsubscribe callable."""
        self._route_visibility_listeners.add(callback)

        def _unsubscribe() -> None:
            self._route_visibility_listeners.discard(callback)

        return _unsubscribe

    def register_route_visibility(self, descriptors: Iterable[Any]) -> None:
        """Index UI-route symbols and their visibility dependency keys (#192)."""
        self._route_visibility_dep_to_symbols.clear()
        self._symbol_route_lookup.clear()
        self._symbol_route_visible.clear()
        for item in descriptors:
            if not isinstance(item, Mapping):
                continue
            if not bool(item.get(CONF_UI_ROUTE_SYMBOL)):
                continue
            devid = str(item.get("devid") or "").strip()
            symbol = str(item.get("symbol") or "").strip()
            if not devid or not symbol:
                continue
            lookup_key = f"{devid}:{symbol}"
            route_name = str(item.get(CONF_ROUTE_VISIBILITY_NAME) or "").strip()
            route_path = str(item.get(CONF_ROUTE_VISIBILITY_PATH) or "").strip()
            self._symbol_route_lookup[lookup_key] = (devid, symbol, route_name, route_path)
            deps = item.get(CONF_ROUTE_VISIBILITY_DEPS)
            if isinstance(deps, list):
                for dep in deps:
                    if isinstance(dep, str) and dep.strip():
                        self._route_visibility_dep_to_symbols.setdefault(dep.strip(), set()).add(symbol)

    def route_visible_for_symbol(self, devid: str, symbol: str) -> bool:
        """Return whether the everyday-UI route for *symbol* is currently visible."""
        lookup_key = f"{devid}:{symbol}"
        if lookup_key not in self._symbol_route_lookup:
            return True
        return bool(self._symbol_route_visible.get(lookup_key, True))

    async def refresh_route_visibility(self, symbols: set[str] | None = None) -> None:
        """Re-evaluate SPA route visibility for indexed UI-route symbols."""
        if not self._symbol_route_lookup:
            return
        resolver = await self._async_get_resolver()
        if resolver is None:
            return
        changed: list[tuple[str, str, bool]] = []
        flat_by_devid: dict[str, dict[str, Any]] = {}
        for lookup_key, (devid, symbol, route_name, route_path) in self._symbol_route_lookup.items():
            if symbols is not None and symbol not in symbols:
                continue
            if devid not in flat_by_devid:
                flat_by_devid[devid] = self.store.flatten_for_devid(devid)
            flat_values = flat_by_devid[devid]
            menu = await self._menu_for_devid(devid, resolver)
            if menu is None:
                continue
            route_match = self._find_menu_route(menu, route_name=route_name, route_path=route_path)
            if route_match is None:
                continue
            route, ancestors = route_match
            visible, _reason = ParamResolver.route_visibility_diagnostics(
                route,
                ancestors=ancestors,
                flat_values=flat_values,
                all_panels=True,
                web_ui_only=True,
            )
            previous = self._symbol_route_visible.get(lookup_key, True)
            self._symbol_route_visible[lookup_key] = visible
            if visible != previous:
                changed.append((devid, symbol, visible))
        for devid, symbol, visible in changed:
            for callback in tuple(self._route_visibility_listeners):
                try:
                    callback(devid, symbol, visible)
                except Exception:
                    LOGGER.exception("Route visibility listener failed for %s/%s", devid, symbol)

    @staticmethod
    def _parse_device_menu_id(raw: Any) -> int | None:
        """Coerce stored ``device_menu`` to int (bool excluded; digit strings allowed)."""
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped.isdigit():
                return int(stripped)
        return None

    async def _menu_for_devid(self, devid: str, resolver: ParamResolver) -> Any | None:
        if devid in self._menu_cache:
            return self._menu_cache[devid]
        meta = self.modules_meta.get(devid)
        if not isinstance(meta, Mapping):
            return None
        device_menu = self._parse_device_menu_id(meta.get("device_menu"))
        if device_menu is None:
            return None
        perms_raw = meta.get("permissions")
        permissions = [str(perm) for perm in perms_raw] if isinstance(perms_raw, list) else []
        try:
            menu = await resolver.get_module_menu(device_menu=device_menu, permissions=permissions)
        except Exception:
            LOGGER.debug("Menu fetch failed for route visibility devid=%s", devid, exc_info=True)
            return None
        self._menu_cache[devid] = menu
        return menu

    @staticmethod
    def _find_menu_route(menu: Any, *, route_name: str, route_path: str) -> tuple[Any, tuple[Any, ...]] | None:
        routes = getattr(menu, "routes", None)
        if not isinstance(routes, list):
            return None
        for route, ancestors in ParamResolver._iter_routes_with_ancestors(routes):
            name = str(getattr(route, "name", "") or "")
            path = str(getattr(route, "path", "") or "")
            if route_name and name == route_name:
                return route, ancestors
            if route_path and path == route_path:
                return route, ancestors
        return None

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

    def add_cloud_session_listener(self, callback: CloudSessionCallback) -> Callable[[], None]:
        """Register a library↔cloud session listener and return unsubscribe callable."""
        self._cloud_session_listeners.add(callback)

        def _remove() -> None:
            self._cloud_session_listeners.discard(callback)

        return _remove

    def add_live_push_listener(self, callback: LivePushCallback) -> Callable[[], None]:
        """Register a live-push health listener and return unsubscribe callable."""
        self._live_push_listeners.add(callback)

        def _remove() -> None:
            self._live_push_listeners.discard(callback)

        return _remove

    def add_event_feed_listener(self, callback: EventFeedCallback) -> Callable[[], None]:
        """Register a module alarms/activity event-feed listener and return unsubscribe callable."""
        self._event_feed_listeners.add(callback)

        def _remove() -> None:
            self._event_feed_listeners.discard(callback)

        return _remove

    def module_online(self, devid: str) -> bool | None:
        """Return cached module online state, or ``None`` if not yet known."""
        return self._module_online.get(devid)

    def cloud_session_up(self) -> bool | None:
        """Return cached library↔cloud Socket.IO session state, or ``None`` if unknown."""
        return self._cloud_session_up

    def cloud_session_outage(self) -> dict[str, float | str | None]:
        """Return cached cloud-session outage attrs (``down_since`` / ``reason`` / ``last_*``)."""
        return dict(self._cloud_session_outage)

    def live_push_health(self) -> dict[str, float | bool | None]:
        """Return cached live-push health (``push_healthy`` / ``live_stale_for_s`` / ``last_resumed_*``)."""
        return dict(self._live_push_health)

    def module_outage(self, devid: str) -> dict[str, float | str | None]:
        """Return cached module↔cloud outage attrs for *devid*."""
        snapshot = self._module_outage.get(devid)
        return dict(snapshot) if isinstance(snapshot, dict) else {}

    @property
    def supports_module_connectivity(self) -> bool:
        """Return whether the gateway exposes the module connectivity API."""
        return callable(getattr(self.gateway, "on_module_connectivity", None)) and callable(
            getattr(self.gateway, "module_online", None)
        )

    @property
    def supports_cloud_session(self) -> bool:
        """Return whether the gateway exposes library↔cloud session callbacks."""
        return callable(getattr(self.gateway, "on_cloud_session", None)) and callable(
            getattr(self.gateway, "ws_session_up", None)
        )

    @property
    def supports_live_push(self) -> bool:
        """Return whether the gateway exposes live ParamUpdate push-health APIs."""
        return callable(getattr(self.gateway, "on_live_push", None)) and callable(getattr(self.gateway, "live_push_health", None))

    @property
    def supports_alarm_quantity(self) -> bool:
        """Return whether the gateway exposes alarm-quantity push callbacks (#254)."""
        return callable(getattr(self.gateway, "on_alarm_quantity", None))

    @property
    def supports_module_alarms(self) -> bool:
        """Return whether the API client exposes module alarms list helpers (#222)."""
        return callable(getattr(self.api, "modules_alarms", None)) and callable(getattr(self.api, "modules_alarms_history", None))

    def alarms_current(self, devid: str) -> list[dict[str, Any]]:
        """Return cached active alarms for *devid* (empty when unknown)."""
        return list(self._alarms_current.get(devid, ()))

    def alarms_feed_ready(self, devid: str) -> bool:
        """Return whether alarms REST data loaded successfully for *devid*."""
        return self._alarms_feed_loaded.get(str(devid or "").strip()) is True

    def alarms_history(self, devid: str) -> list[dict[str, Any]]:
        """Return cached history alarms for *devid* (empty when unknown)."""
        return list(self._alarms_history.get(devid, ()))

    async def async_get_alarm_chrome_labels(self) -> dict[str, str] | None:
        """Return SPA ``alarm.currentAlarms`` / ``alarm.historyAlarms`` labels, or ``None``.

        Fail closed when the catalog/i18n cannot supply both chrome strings so
        entities are never created with hardcoded language fallbacks.
        """
        async with self._alarm_assets_lock:
            cached = self._alarm_chrome_labels
            if cached is not None:
                return cached or None
            labels = await self._load_alarm_chrome_labels()
            self._alarm_chrome_labels = labels
            return labels or None

    async def async_refresh_alarms(self, devid: str) -> None:
        """Fetch active + history alarms for *devid*, normalize, and notify listeners.

        No-ops when the installed pybragerone build lacks the alarms REST helpers.
        Concurrent refreshes for the same devid share one in-flight task.
        """
        devid_key = str(devid or "").strip()
        if not devid_key or not self.supports_module_alarms:
            return

        existing = self._alarms_refresh_tasks.get(devid_key)
        if existing is not None and not existing.done():
            await existing
            return

        task = asyncio.create_task(self._async_refresh_alarms_impl(devid_key), name=f"habragerone-alarms-{devid_key}")
        self._alarms_refresh_tasks[devid_key] = task
        try:
            await task
        finally:
            if self._alarms_refresh_tasks.get(devid_key) is task:
                self._alarms_refresh_tasks.pop(devid_key, None)

    async def _async_refresh_alarms_impl(self, devid_key: str) -> None:
        current_fn = getattr(self.api, "modules_alarms", None)
        history_fn = getattr(self.api, "modules_alarms_history", None)
        if not callable(current_fn) or not callable(history_fn):
            return

        await self._ensure_alarm_name_maps()

        try:
            current_result = await current_fn([devid_key], page=_ALARMS_PAGE, limit=_ALARMS_LIMIT, return_data=True)
            history_result = await history_fn([devid_key], page=_ALARMS_PAGE, limit=_ALARMS_LIMIT, return_data=True)
        except Exception:
            LOGGER.exception("Failed to refresh module alarms for devid=%s", devid_key)
            self._alarms_feed_loaded[devid_key] = False
            self._notify_event_feed_listeners(devid_key)
            return

        if not (_module_events_rest_ok(current_result) and _module_events_rest_ok(history_result)):
            LOGGER.warning("Module alarms REST returned non-success status for devid=%s", devid_key)
            self._alarms_feed_loaded[devid_key] = False
            self._notify_event_feed_listeners(devid_key)
            return

        current_rows = _extract_alarm_rows(current_result)
        history_rows = _extract_alarm_rows(history_result)
        self._alarms_current[devid_key] = [self._normalize_alarm_row(row, default_devid=devid_key) for row in current_rows]
        self._alarms_history[devid_key] = [self._normalize_alarm_row(row, default_devid=devid_key) for row in history_rows]
        self._alarms_feed_loaded[devid_key] = True
        self._notify_event_feed_listeners(devid_key)

    def _notify_event_feed_listeners(self, devid: str) -> None:
        for callback in list(self._event_feed_listeners):
            try:
                callback(devid)
            except Exception:
                LOGGER.exception("Event feed listener failed for devid=%s", devid)

    def _normalize_alarm_row(self, row: Mapping[str, Any], *, default_devid: str) -> dict[str, Any]:
        """Normalize one REST alarm row into the HA attributes shape."""
        raw_id = row.get("id")
        alarm_id: int | None
        if isinstance(raw_id, bool):
            alarm_id = None
        elif isinstance(raw_id, int):
            alarm_id = raw_id
        elif isinstance(raw_id, float) and raw_id.is_integer():
            alarm_id = int(raw_id)
        elif isinstance(raw_id, str) and raw_id.strip().isdigit():
            alarm_id = int(raw_id.strip())
        else:
            alarm_id = None

        row_devid = row.get("devid")
        devid = str(row_devid).strip() if isinstance(row_devid, str) and row_devid.strip() else default_devid

        name: str | None = None
        if alarm_id is not None:
            name = _resolve_alarm_row_name(
                alarm_id,
                alarm_names=self._alarm_names,
                errors_i18n=self._errors_i18n,
            )

        created_at = row.get("created_at")
        finished_at = row.get("finished_at")
        return {
            "id": alarm_id,
            "name": name,
            "devid": devid,
            "created_at": created_at if isinstance(created_at, str) else None,
            "finished_at": finished_at if isinstance(finished_at, str) else None,
        }

    async def _load_alarm_chrome_labels(self) -> dict[str, str]:
        """Load ``alarm.*`` chrome labels from LiveAssetsCatalog (empty on failure)."""
        catalog = _try_live_assets_catalog(self.api)
        if catalog is None:
            return {}

        lang = (self.language or "").strip()
        if not lang:
            return {}

        try:
            # ``get_i18n`` auto-loads the index via ``LiveAssetsCatalog._ensure_index_loaded``.
            # Do not call ``refresh_index()`` here — it requires an explicit index URL.
            get_i18n = getattr(catalog, "get_i18n", None)
            if not callable(get_i18n):
                return {}
            alarm_ns = await get_i18n(lang, "alarm")
        except Exception:
            LOGGER.debug("Failed to load alarm chrome i18n", exc_info=True)
            return {}

        if not isinstance(alarm_ns, Mapping):
            return {}
        out: dict[str, str] = {}
        for key in _ALARM_CHROME_KEYS:
            value = alarm_ns.get(key)
            if isinstance(value, str) and value.strip():
                out[key] = value.strip()
        if all(key in out for key in _ALARM_CHROME_KEYS):
            return out
        return {}

    async def _ensure_alarm_name_maps(self) -> None:
        """Best-effort load of AlarmName enum + ``errors.*`` i18n for row titles."""
        async with self._alarm_assets_lock:
            if self._alarm_names_loaded:
                return
            await self._load_alarm_name_maps()
            if self._alarm_names and self._errors_i18n:
                self._alarm_names_loaded = True

    async def _load_alarm_name_maps(self) -> None:
        parse_fn, _resolve_fn = _alarm_name_helpers()
        lang = (self.language or "").strip()
        catalog = _try_live_assets_catalog(self.api)
        if catalog is None:
            return

        try:
            get_i18n = getattr(catalog, "get_i18n", None)
            if callable(get_i18n) and lang:
                errors = await get_i18n(lang, "errors")
                if isinstance(errors, Mapping):
                    self._errors_i18n = dict(errors)
            if callable(parse_fn):
                fetch_source = getattr(catalog, "fetch_alarm_name_source", None)
                source: str | bytes | None = None
                if callable(fetch_source):
                    source = await fetch_source()
                if source:
                    parsed = parse_fn(source)
                    if isinstance(parsed, dict):
                        self._alarm_names = {
                            int(key): str(value)
                            for key, value in parsed.items()
                            if isinstance(key, int) and isinstance(value, str)
                        }
        except Exception:
            LOGGER.debug("Failed to load AlarmName / errors i18n maps", exc_info=True)

    @property
    def supports_module_activity(self) -> bool:
        """Return whether the API client exposes ``modules_activity`` (#223)."""
        return callable(getattr(self.api, "modules_activity", None))

    def activity(self, devid: str) -> list[dict[str, Any]]:
        """Return cached activity rows for *devid* (empty when unknown)."""
        return list(self._activity.get(devid, ()))

    def activity_feed_ready(self, devid: str) -> bool:
        """Return whether activity REST data loaded successfully for *devid*."""
        return self._activity_feed_loaded.get(str(devid or "").strip()) is True

    async def async_get_activity_index_label(self) -> str | None:
        """Return SPA ``routes.activity.index`` entity name, or ``None``.

        Fail closed when catalog/i18n cannot supply the chrome string so the
        sensor is never created with a hardcoded language fallback.
        """
        async with self._activity_assets_lock:
            if self._activity_assets_loaded:
                label = self._activity_index_label
                return label if isinstance(label, str) and label.strip() else None
            await self._load_activity_assets()
            self._activity_assets_loaded = True
            label = self._activity_index_label
            return label if isinstance(label, str) and label.strip() else None

    async def async_refresh_activity(self, devid: str) -> None:
        """Fetch first-page activity rows for *devid*, normalize, and notify listeners.

        Uses the SPA default window (``page=1``, ``limit=20``). No-ops when the
        installed pybragerone build lacks ``modules_activity``. Concurrent
        refreshes for the same devid share one in-flight task.
        """
        devid_key = str(devid or "").strip()
        if not devid_key or not self.supports_module_activity:
            return

        existing = self._activity_refresh_tasks.get(devid_key)
        if existing is not None and not existing.done():
            await existing
            return

        task = asyncio.create_task(
            self._async_refresh_activity_impl(devid_key),
            name=f"habragerone-activity-{devid_key}",
        )
        self._activity_refresh_tasks[devid_key] = task
        try:
            await task
        finally:
            if self._activity_refresh_tasks.get(devid_key) is task:
                self._activity_refresh_tasks.pop(devid_key, None)

    async def _async_refresh_activity_impl(self, devid_key: str) -> None:
        activity_fn = getattr(self.api, "modules_activity", None)
        if not callable(activity_fn):
            return

        await self._ensure_activity_assets()
        resolver = await self._async_get_resolver()

        try:
            result = await activity_fn(
                [devid_key],
                page=_ACTIVITY_PAGE,
                limit=_ACTIVITY_LIMIT,
                return_data=True,
            )
        except Exception:
            LOGGER.exception("Failed to refresh module activity for devid=%s", devid_key)
            self._activity_feed_loaded[devid_key] = False
            self._notify_event_feed_listeners(devid_key)
            return

        if not _module_events_rest_ok(result):
            LOGGER.warning("Module activity REST returned non-success status for devid=%s", devid_key)
            self._activity_feed_loaded[devid_key] = False
            self._notify_event_feed_listeners(devid_key)
            return

        rows = _extract_activity_rows(result)
        self._activity[devid_key] = [
            await self._normalize_activity_row(row, default_devid=devid_key, resolver=resolver) for row in rows
        ]
        self._activity_feed_loaded[devid_key] = True
        self._notify_event_feed_listeners(devid_key)

    async def _ensure_activity_assets(self) -> None:
        """Best-effort load of activity chrome + ``activity.state.*`` i18n."""
        async with self._activity_assets_lock:
            if self._activity_assets_loaded:
                return
            try:
                await self._load_activity_assets()
            finally:
                self._activity_assets_loaded = True

    async def _load_activity_assets(self) -> None:
        """Load ``routes.activity.index`` and ``activity.state`` labels from the catalog."""
        catalog = _try_live_assets_catalog(self.api)
        lang = (self.language or "").strip()
        if catalog is None or not lang:
            self._activity_index_label = None
            return

        try:
            get_i18n = getattr(catalog, "get_i18n", None)
            if not callable(get_i18n):
                self._activity_index_label = None
                return

            routes_ns = await get_i18n(lang, "routes")
            index_label: str | None = None
            if isinstance(routes_ns, Mapping):
                activity_routes = routes_ns.get("activity")
                if isinstance(activity_routes, Mapping):
                    raw_index = activity_routes.get("index")
                    if isinstance(raw_index, str) and raw_index.strip():
                        index_label = raw_index.strip()
            self._activity_index_label = index_label

            activity_ns = await get_i18n(lang, "activity")
            state_map: dict[str, str] = {}
            if isinstance(activity_ns, Mapping):
                state_ns = activity_ns.get("state")
                if isinstance(state_ns, Mapping):
                    for key, value in state_ns.items():
                        if isinstance(key, str) and isinstance(value, str) and value.strip():
                            state_map[key.strip()] = value.strip()
            self._activity_state_i18n = state_map
        except Exception:
            LOGGER.debug("Failed to load activity chrome / state i18n", exc_info=True)
            self._activity_index_label = None

    async def _normalize_activity_row(
        self,
        row: Mapping[str, Any],
        *,
        default_devid: str,
        resolver: Any,
    ) -> dict[str, Any]:
        """Normalize one REST activity row into the HA attributes shape."""
        raw_id = row.get("id")
        activity_id: int | None
        if isinstance(raw_id, bool):
            activity_id = None
        elif isinstance(raw_id, int):
            activity_id = raw_id
        elif isinstance(raw_id, float) and raw_id.is_integer():
            activity_id = int(raw_id)
        elif isinstance(raw_id, str) and raw_id.strip().isdigit():
            activity_id = int(raw_id.strip())
        else:
            activity_id = None

        devid = _activity_row_devid(row, default_devid=default_devid)

        parameter_key_raw = row.get("name")
        parameter_key = parameter_key_raw.strip() if isinstance(parameter_key_raw, str) and parameter_key_raw.strip() else None
        parameter = await _resolve_activity_i18n_token(parameter_key, resolver=resolver)

        unit_code = row.get("unit")
        value_raw = _activity_value_scalar(row.get("value"))
        # Live SPA rows expose the scalar previous value as camelCase ``prevValue``.
        # Snake-case ``prev_value`` is a nested param snapshot (``{P*: {n: {v,u}}}``),
        # not the display scalar — prefer camelCase, then fall back.
        prev_raw = row.get("prevValue")
        if prev_raw is None:
            prev_raw = row.get("prev_value")
        prev_value_raw = _activity_value_scalar(prev_raw)

        value = await _resolve_activity_display_value(value_raw, unit_code=unit_code, resolver=resolver)
        prev_value = await _resolve_activity_display_value(prev_value_raw, unit_code=unit_code, resolver=resolver)

        state_key_raw = row.get("state")
        state_key = state_key_raw.strip() if isinstance(state_key_raw, str) and state_key_raw.strip() else None
        state_label: str | None = None
        if state_key is not None:
            mapped = self._activity_state_i18n.get(state_key)
            if isinstance(mapped, str) and mapped.strip():
                state_label = mapped.strip()

        created_at = row.get("created_at")
        created_by = _activity_created_by(row.get("user"))

        return {
            "id": activity_id,
            "devid": devid,
            "parameter": parameter,
            "parameter_key": parameter_key,
            "value": value,
            "value_raw": value_raw,
            "prev_value": prev_value,
            "prev_value_raw": prev_value_raw,
            "state": state_label,
            "state_key": state_key,
            "created_at": created_at if isinstance(created_at, str) else None,
            "created_by": created_by,
        }

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

    def _seed_cloud_session_from_gateway(self) -> None:
        """Pull initial library↔cloud session bit from the gateway after start."""
        if not self.supports_cloud_session:
            return
        up = self.gateway.ws_session_up()
        if isinstance(up, bool):
            self._apply_cloud_session(up)
        outage_fn = getattr(self.gateway, "cloud_session_outage", None)
        if callable(outage_fn):
            snapshot = outage_fn()
            if isinstance(snapshot, dict):
                outage = extract_outage_fields(snapshot)
                # Empty dict / all-None from older wheels must not wipe last_*.
                if outage_snapshot_has_values(outage):
                    self._cloud_session_outage = outage

    def _seed_live_push_from_gateway(self) -> None:
        """Pull initial live-push health snapshot from the gateway after start."""
        if not self.supports_live_push:
            return
        health_fn = getattr(self.gateway, "live_push_health", None)
        if not callable(health_fn):
            return
        snapshot = health_fn()
        if isinstance(snapshot, dict):
            health = extract_live_push_fields(snapshot)
            if live_push_snapshot_has_values(health):
                self._live_push_health = health

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
        outage = extract_outage_fields(event)
        # Older wheels / metadata-only events may omit outage fields; do not wipe last_*.
        if outage_snapshot_has_values(outage):
            self._module_outage[devid] = outage
        self._apply_module_online(
            devid,
            online,
            connected_at=connected_at if isinstance(connected_at, int) else None,
            gateway=gateway if isinstance(gateway, dict) else None,
            online_changed=online_changed,
        )

    def _on_gateway_cloud_session(self, event: Any) -> None:
        """Handle ``CloudSessionConnectivity`` (or duck-typed) events from the gateway."""
        up = getattr(event, "up", None)
        if not isinstance(up, bool):
            return
        outage = extract_outage_fields(event)
        if outage_snapshot_has_values(outage):
            self._cloud_session_outage = outage
        self._apply_cloud_session(up)

    def _on_gateway_live_push(self, event: Any) -> None:
        """Handle ``LivePushHealth`` (or duck-typed) events from the gateway."""
        health = extract_live_push_fields(event)
        if live_push_snapshot_has_values(health):
            self._live_push_health = health
        for callback in list(self._live_push_listeners):
            try:
                callback()
            except Exception:
                LOGGER.exception("Live-push listener failed")

    def _on_gateway_alarm_quantity(self, event: Any) -> None:
        """Refresh alarm feed when SPA alarm count changes for a subscribed module."""
        if not getattr(event, "changed", True):
            return
        devid = str(getattr(event, "devid", "") or "").strip()
        if not devid:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        task = asyncio.create_task(
            self.async_refresh_alarms(devid),
            name=f"habragerone-alarms-qty-{devid}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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
        if previous is not None and previous is not online:
            LOGGER.warning(
                "Module online state changed: devid=%s online=%s connectedAt=%s",
                devid,
                online,
                connected_at,
            )
        for callback in list(self._connectivity_listeners):
            try:
                self._invoke_connectivity_listener(callback, devid, online, flipped)
            except Exception:
                LOGGER.exception("Connectivity listener failed for devid=%s", devid)

    def _apply_cloud_session(self, up: bool) -> None:
        """Update library↔cloud session cache and notify listeners on flips or first seed.

        The second listener argument is ``True`` on a real flip or the first known
        value (seed); idempotent repeats do not notify.
        """
        previous = self._cloud_session_up
        self._cloud_session_up = up
        flipped = previous is not up
        if not flipped and previous is not None:
            return
        for callback in list(self._cloud_session_listeners):
            try:
                callback(up, flipped or previous is None)
            except Exception:
                LOGGER.exception("Cloud session listener failed")

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
            raw_min=(
                descriptor.get("min")
                if isinstance(descriptor.get("min"), int | float) and not isinstance(descriptor.get("min"), bool)
                else None
            ),
            raw_max=(
                descriptor.get("max")
                if isinstance(descriptor.get("max"), int | float) and not isinstance(descriptor.get("max"), bool)
                else None
            ),
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
            self._schedule_activity_refresh_after_write(devid)
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
            self._schedule_activity_refresh_after_write(devid)
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
        self._schedule_activity_refresh_after_write(devid)

    def _schedule_activity_refresh_after_write(self, devid: str) -> None:
        """Refresh activity feed after a successful HA write (SPA logs parameter changes)."""
        devid_key = str(devid or "").strip()
        if not devid_key or not self.supports_module_activity:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        task = asyncio.create_task(
            self.async_refresh_activity(devid_key),
            name=f"habragerone-activity-after-write-{devid_key}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def async_warm_status_resolver(self, symbols: Iterable[str] | None = None) -> None:
        """Build ``ParamResolver``, prefetch mappings, and pre-resolve STATUS labels (#204)."""
        symbol_list = list(dict.fromkeys(str(symbol).strip() for symbol in (symbols or []) if str(symbol).strip()))
        if not symbol_list:
            return
        resolver = await self._async_get_resolver()
        if resolver is None:
            return
        try:
            await resolver.prefetch_param_mappings(symbol_list)
            status_symbols = [symbol for symbol in symbol_list if symbol.startswith("STATUS_")]
            if not status_symbols:
                return
            semaphore = asyncio.Semaphore(16)

            async def _resolve_one(symbol: str) -> None:
                async with semaphore:
                    label = await self._resolve_status_label_uncached(symbol, resolver=resolver)
                if label is not None:
                    self._status_label_cache[symbol] = label

            async with asyncio.TaskGroup() as group:
                for symbol in status_symbols:
                    group.create_task(_resolve_one(symbol))
        except Exception:
            LOGGER.debug("STATUS resolver warm-up failed; continuing without prefetch", exc_info=True)

    def peek_status_label(self, symbol: str) -> Any | None:
        """Return a pre-warmed STATUS label without triggering resolver I/O."""
        if not symbol.startswith("STATUS_"):
            return None
        return self._status_label_cache.get(symbol)

    async def async_resolve_status_label(self, symbol: str) -> Any | None:
        """Resolve STATUS_* value exactly as parser/UI logic does."""
        if not symbol.startswith("STATUS_"):
            return None
        cached = self._status_label_cache.get(symbol)
        if cached is not None:
            return cached
        label = await self._resolve_status_label_uncached(symbol)
        if label is not None:
            self._status_label_cache[symbol] = label
        return label

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

    async def _async_get_resolver(self) -> ParamResolver | None:
        if self._status_resolver is not None:
            return self._status_resolver
        async with self._resolver_lock:
            try:
                if self._status_resolver is None:
                    self._status_resolver = ParamResolver.from_api(
                        api=self.api,
                        store=self.store,
                        lang=self.language,
                    )
            except Exception:
                LOGGER.debug("ParamResolver init failed", exc_info=True)
                return None
            return self._status_resolver

    async def _resolve_status_label_uncached(
        self,
        symbol: str,
        *,
        resolver: ParamResolver | None = None,
    ) -> Any | None:
        resolved = await self._async_resolve_symbol(symbol, resolver=resolver)
        if resolved is None:
            return None
        if isinstance(resolved.value_label, str) and resolved.value_label.strip():
            return resolved.value_label.strip()
        return resolved.value

    async def _async_resolve_symbol(
        self,
        symbol: str,
        *,
        resolver: ParamResolver | None = None,
    ) -> Any | None:
        active_resolver = resolver or await self._async_get_resolver()
        if active_resolver is None:
            return None
        try:
            return await active_resolver.resolve_value(symbol)
        except Exception:
            return None

    async def _dispatch_updates(self) -> None:
        async for update in self.gateway.bus.subscribe():
            self._status_label_cache.clear()
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
            update_key = f"{update.pool}.{update.chan}{update.idx}"
            # Store and dispatcher are independent bus subscribers; upsert first so
            # route visibility sees this delta rather than the previous snapshot.
            if getattr(update, "value", None) is not None:
                self.store.upsert(update_key, update.value, devid=update.devid)
            affected_symbols = self._route_visibility_dep_to_symbols.get(update_key)
            if affected_symbols:
                await self.refresh_route_visibility(set(affected_symbols))
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


def _module_events_rest_ok(result: Any) -> bool:
    """Return whether a ``return_data=True`` module-events REST call succeeded."""
    if not isinstance(result, tuple) or not result:
        return False
    status = result[0]
    if status not in (200, 204):
        return False
    if len(result) >= 2:
        payload = result[1]
        if isinstance(payload, Mapping) and payload.get("status") is False:
            return False
    return True


def _extract_activity_rows(result: Any) -> list[Mapping[str, Any]]:
    """Pull activity row mappings from a ``modules_activity`` ``return_data`` result."""
    payload: Any = result
    if isinstance(result, tuple) and len(result) >= 2:
        payload = result[1]
    if not isinstance(payload, Mapping):
        return []
    activities = payload.get("activities")
    if isinstance(activities, list):
        return [row for row in activities if isinstance(row, Mapping)]
    if isinstance(activities, Mapping):
        data = activities.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, Mapping)]
    return []


def _activity_row_devid(row: Mapping[str, Any], *, default_devid: str) -> str:
    """Resolve devid from a row or nested ``module`` object."""
    row_devid = row.get("devid")
    if isinstance(row_devid, str) and row_devid.strip():
        return row_devid.strip()
    module = row.get("module")
    if isinstance(module, Mapping):
        module_devid = module.get("devid")
        if isinstance(module_devid, str) and module_devid.strip():
            return module_devid.strip()
    return default_devid


def _activity_value_scalar(raw: Any) -> Any:
    """Unwrap nested SPA value maps to a display/raw scalar when possible.

    Handles:
    - plain scalars
    - ``{"value": ...}`` / ``{"prevValue": ...}`` wrappers
    - nested param snapshots ``{"P6": {"219": {"v": 2, "u": 38}}}``
    """
    if isinstance(raw, Mapping):
        if "value" in raw:
            return _activity_value_scalar(raw.get("value"))
        if "prevValue" in raw:
            return _activity_value_scalar(raw.get("prevValue"))
        if "v" in raw:
            return _activity_value_scalar(raw.get("v"))
        for nested in raw.values():
            if isinstance(nested, Mapping):
                extracted = _activity_value_scalar(nested)
                if extracted is not None:
                    return extracted
        return None
    return raw


def _activity_created_by(raw: Any) -> str | None:
    """Extract the activity author label from a string or ``{name, id}`` user object."""
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, Mapping):
        name = raw.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


async def _resolve_activity_i18n_token(token: str | None, *, resolver: Any) -> str | None:
    """Best-effort resolve of dotted i18n tokens via ParamResolver."""
    if not isinstance(token, str) or not token.strip() or resolver is None:
        return None
    resolve_token = getattr(resolver, "_resolve_i18n_token", None)
    if not callable(resolve_token):
        return None
    try:
        label = await resolve_token(token.strip())
    except Exception:
        return None
    return label.strip() if isinstance(label, str) and label.strip() else None


async def _resolve_activity_display_value(raw: Any, *, unit_code: Any, resolver: Any) -> Any:
    """Map a raw activity value through unit enum tables and numeric transforms."""
    if resolver is None or unit_code is None or raw is None:
        return raw
    resolve_display = getattr(resolver, "resolve_raw_display_value", None)
    if callable(resolve_display):
        try:
            return await resolve_display(raw, unit_code=unit_code)
        except Exception:
            LOGGER.debug("resolve_raw_display_value failed", exc_info=True)
    resolve_unit = getattr(resolver, "resolve_unit", None)
    if not callable(resolve_unit):
        return raw
    try:
        unit = await resolve_unit(unit_code)
    except Exception:
        return raw
    if not isinstance(unit, Mapping):
        return raw

    mapping_label = getattr(resolver, "_unit_mapping_value_label", None)
    label: str | None = None
    if callable(mapping_label):
        try:
            mapped = mapping_label(unit, raw)
        except Exception:
            mapped = None
        if isinstance(mapped, str) and mapped.strip():
            label = mapped.strip()
    if label is None:
        for key in (raw, str(raw)):
            mapped = unit.get(key)
            if isinstance(mapped, str) and mapped.strip():
                label = mapped.strip()
                break
    if label is None:
        return raw
    resolved = await _resolve_activity_i18n_token(label, resolver=resolver)
    return resolved or label


def _extract_alarm_rows(result: Any) -> list[Mapping[str, Any]]:
    """Pull alarm row mappings from a ``modules_alarms*`` ``return_data`` result."""
    payload: Any = result
    if isinstance(result, tuple) and len(result) >= 2:
        payload = result[1]
    if not isinstance(payload, Mapping):
        return []
    alarms = payload.get("alarms")
    if isinstance(alarms, list):
        return [row for row in alarms if isinstance(row, Mapping)]
    if isinstance(alarms, Mapping):
        data = alarms.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, Mapping)]
    return []


def _alarm_name_helpers() -> tuple[Any, Any]:
    """Return AlarmName helpers when the installed library exposes them."""
    return _parse_alarm_name_enum, _resolve_alarm_label


def _try_live_assets_catalog(api: Any) -> Any | None:
    """Construct ``LiveAssetsCatalog(api)`` when the installed library supports it."""
    try:
        from pybragerone.models.catalog import LiveAssetsCatalog as catalog_cls
    except ImportError:
        LOGGER.debug("LiveAssetsCatalog unavailable; alarm chrome/name maps skipped")
        return None
    try:
        return catalog_cls(api)
    except TypeError:
        # Unit-test stub sets ``LiveAssetsCatalog = object``.
        return None


def _resolve_alarm_row_name(
    alarm_id: int,
    *,
    alarm_names: Mapping[int, str],
    errors_i18n: Mapping[str, Any],
) -> str | None:
    """Resolve ``errors.*`` label for one alarm id; leave null when helpers/maps miss."""
    _parse_fn, resolve_fn = _alarm_name_helpers()
    if callable(resolve_fn):
        try:
            label = resolve_fn(alarm_id, alarm_names=alarm_names, errors_i18n=errors_i18n)
        except Exception:
            return None
        return label if isinstance(label, str) and label.strip() else None
    key = alarm_names.get(alarm_id)
    if not isinstance(key, str) or not key.startswith("ERROR_"):
        return None
    value = errors_i18n.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None
