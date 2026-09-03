"""Patch-coverage tests for release/2026.9 runtime helpers and edge paths."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import (  # noqa: E402
    CONF_ROUTE_VISIBILITY_DEPS,
    CONF_ROUTE_VISIBILITY_NAME,
    CONF_ROUTE_VISIBILITY_PATH,
    CONF_UI_ROUTE_SYMBOL,
)
from custom_components.habragerone.runtime import (  # noqa: E402
    BragerRuntime,
    _activity_created_by,
    _activity_row_devid,
    _activity_value_scalar,
    _alarm_name_helpers,
    _extract_activity_rows,
    _extract_alarm_rows,
    _import_alarm_name_helpers,
    _module_events_rest_ok,
    _resolve_activity_display_value,
    _resolve_activity_i18n_token,
    _resolve_alarm_row_name,
    _try_live_assets_catalog,
)
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402


def test_register_route_visibility_skips_invalid_descriptors() -> None:
    """Only well-formed UI-route descriptors populate the visibility index."""
    runtime, *_rest = make_runtime()
    runtime.register_route_visibility(
        [
            "not-a-mapping",
            {"devid": "", "symbol": "PARAM_1", CONF_UI_ROUTE_SYMBOL: True},
            {"devid": "dev1", "symbol": "", CONF_UI_ROUTE_SYMBOL: True},
            {
                "devid": "dev1",
                "symbol": "PARAM_9",
                CONF_UI_ROUTE_SYMBOL: False,
            },
            {
                "devid": "dev1",
                "symbol": "PARAM_177",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "MAINMENU_X",
                CONF_ROUTE_VISIBILITY_PATH: "timezones",
                CONF_ROUTE_VISIBILITY_DEPS: ["P1.s0", "", "P6.v219"],
            },
        ]
    )
    assert runtime._symbol_route_lookup == {
        "dev1:PARAM_177": ("dev1", "PARAM_177", "MAINMENU_X", "timezones"),
    }
    assert runtime._route_visibility_dep_to_symbols["P1.s0"] == {"PARAM_177"}
    assert runtime._route_visibility_dep_to_symbols["P6.v219"] == {"PARAM_177"}


def test_route_visibility_listener_unsubscribe() -> None:
    """add_route_visibility_listener returns an unsubscribe callable."""
    runtime, *_rest = make_runtime()
    seen: list[tuple[str, str, bool]] = []
    remove = runtime.add_route_visibility_listener(lambda devid, symbol, visible: seen.append((devid, symbol, visible)))
    for callback in tuple(runtime._route_visibility_listeners):
        callback("dev1", "PARAM_1", False)
    assert seen == [("dev1", "PARAM_1", False)]
    remove()
    seen.clear()
    for callback in tuple(runtime._route_visibility_listeners):
        callback("dev1", "PARAM_1", True)
    assert seen == []


@pytest.mark.asyncio
async def test_refresh_route_visibility_no_resolver() -> None:
    """Missing ParamResolver leaves visibility state unchanged."""
    with patch.object(BragerRuntime, "_async_get_resolver", AsyncMock(return_value=None)):
        runtime, *_rest = make_runtime()
        runtime.register_route_visibility([{"devid": "dev1", "symbol": "PARAM_177", CONF_UI_ROUTE_SYMBOL: True}])
        await runtime.refresh_route_visibility({"PARAM_177"})
        assert runtime.route_visible_for_symbol("dev1", "PARAM_177") is True


@pytest.mark.asyncio
async def test_refresh_route_visibility_no_menu_or_route() -> None:
    """Menu fetch failures and missing routes are tolerated."""
    runtime, *_rest = make_runtime(modules_meta={"dev1": {"name": "mod"}})
    runtime.register_route_visibility(
        [
            {
                "devid": "dev1",
                "symbol": "PARAM_177",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "MISSING",
                CONF_ROUTE_VISIBILITY_PATH: "missing",
            }
        ]
    )
    resolver = AsyncMock()
    resolver.get_module_menu = AsyncMock(return_value=SimpleNamespace(routes=[]))
    runtime._status_resolver = resolver

    await runtime.refresh_route_visibility({"PARAM_177"})
    assert runtime.route_visible_for_symbol("dev1", "PARAM_177") is True

    runtime.modules_meta["dev1"] = {"name": "mod", "device_menu": "bad", "permissions": []}
    menu = await runtime._menu_for_devid("dev1", resolver)
    assert menu is None


@pytest.mark.asyncio
async def test_refresh_route_visibility_listener_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Listener failures during visibility refresh are logged, not propagated."""
    runtime, *_rest = make_runtime(modules_meta={"dev1": {"device_menu": 0, "permissions": []}})
    runtime.register_route_visibility(
        [
            {
                "devid": "dev1",
                "symbol": "PARAM_177",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "MAINMENU_X",
                CONF_ROUTE_VISIBILITY_PATH: "timezones",
            }
        ]
    )
    route = SimpleNamespace(
        name="MAINMENU_X",
        path="timezones",
        meta=SimpleNamespace(display_dropdown="![]"),
        children=[],
    )
    resolver = AsyncMock()
    resolver.get_module_menu = AsyncMock(return_value=SimpleNamespace(routes=[route]))
    runtime._status_resolver = resolver

    def _boom(_devid: str, _symbol: str, _visible: bool) -> None:
        raise RuntimeError("listener failed")

    runtime.add_route_visibility_listener(_boom)
    with caplog.at_level("ERROR"):
        await runtime.refresh_route_visibility({"PARAM_177"})
        assert "Route visibility listener failed" in caplog.text


@pytest.mark.asyncio
async def test_menu_for_devid_handles_bad_meta_and_fetch_errors(caplog: pytest.LogCaptureFixture) -> None:
    """Menu cache rejects invalid metadata and fetch failures."""
    runtime, *_rest = make_runtime(modules_meta={"dev1": "not-a-mapping"})
    resolver = AsyncMock()
    assert await runtime._menu_for_devid("dev1", resolver) is None

    runtime.modules_meta["dev1"] = {"device_menu": "bad"}
    assert await runtime._menu_for_devid("dev1", resolver) is None

    runtime.modules_meta["dev1"] = {"device_menu": 1, "permissions": ["P1"]}
    resolver.get_module_menu = AsyncMock(side_effect=RuntimeError("offline"))
    with caplog.at_level("DEBUG"):
        assert await runtime._menu_for_devid("dev1", resolver) is None
        assert "Menu fetch failed" in caplog.text


def test_find_menu_route_matches_name_or_path() -> None:
    """Route lookup prefers name, then path."""
    child = SimpleNamespace(name="leaf", path="leaf", children=[])
    route = SimpleNamespace(name="MAINMENU_X", path="timezones", children=[child])
    menu = SimpleNamespace(routes=[route])
    by_name = BragerRuntime._find_menu_route(menu, route_name="MAINMENU_X", route_path="")
    by_path = BragerRuntime._find_menu_route(menu, route_name="", route_path="timezones")
    assert by_name is not None and by_name[0] is route
    assert by_path is not None and by_path[0] is route
    assert BragerRuntime._find_menu_route(menu, route_name="", route_path="missing") is None
    assert BragerRuntime._find_menu_route(SimpleNamespace(routes="bad"), route_name="x", route_path="y") is None


def test_extract_activity_rows_rejects_non_mapping_payload() -> None:
    """Invalid REST payloads yield empty activity row lists."""
    assert _extract_activity_rows((200, "bad")) == []
    assert _extract_activity_rows("not-a-tuple") == []


def test_activity_helpers_cover_nested_shapes() -> None:
    """Activity helper functions unwrap nested module/value shapes."""
    assert _activity_row_devid({"module": {"devid": "M2"}}, default_devid="DEV1") == "M2"
    assert _activity_value_scalar({"P1": {"2": {"v": 9}}}) == 9
    assert _activity_created_by({"name": "  "}) is None


@pytest.mark.asyncio
async def test_resolve_activity_i18n_and_display_value() -> None:
    """Activity display helpers resolve tokens and unit labels."""
    assert await _resolve_activity_i18n_token(None, resolver=None) is None
    assert await _resolve_activity_i18n_token("token", resolver=object()) is None

    resolver = SimpleNamespace(
        _resolve_i18n_token=AsyncMock(return_value="Resolved"),
        resolve_unit=AsyncMock(return_value={"1": "units.one"}),
        _unit_mapping_value_label=lambda _unit, _raw: "mapped.label",
    )
    assert await _resolve_activity_i18n_token("units.one", resolver=resolver) == "Resolved"
    assert await _resolve_activity_display_value(1, unit_code=38, resolver=resolver) == "Resolved"

    display_resolver = SimpleNamespace(
        resolve_raw_display_value=AsyncMock(return_value=5.3),
    )
    assert await _resolve_activity_display_value(53, unit_code=49, resolver=display_resolver) == 5.3

    broken = SimpleNamespace(
        resolve_unit=AsyncMock(side_effect=RuntimeError("boom")),
        _unit_mapping_value_label=lambda *_a: None,
    )
    assert await _resolve_activity_display_value(5, unit_code=1, resolver=broken) == 5

    failing_display = SimpleNamespace(
        resolve_raw_display_value=AsyncMock(side_effect=RuntimeError("display boom")),
        resolve_unit=AsyncMock(return_value={"1": "units.one"}),
        _unit_mapping_value_label=lambda _unit, _raw: "legacy.mapped",
    )
    assert await _resolve_activity_display_value(53, unit_code=49, resolver=failing_display) == "legacy.mapped"


@pytest.mark.asyncio
async def test_normalize_activity_row_coerces_scalar_ids() -> None:
    """Activity row normalization accepts bool/float/string ids."""
    runtime, *_rest = make_runtime()
    runtime._activity_state_i18n = {"ok": "Done"}
    row = await runtime._normalize_activity_row(
        {
            "id": "42",
            "name": "parameters.PARAM_1",
            "unit": 1,
            "value": 2.0,
            "prevValue": 1.0,
            "state": "ok",
            "created_at": "2026-01-01",
            "user": "alice",
        },
        default_devid="DEV1",
        resolver=None,
    )
    assert row["id"] == 42
    assert row["state"] == "Done"
    assert row["created_by"] == "alice"


@pytest.mark.asyncio
async def test_async_refresh_activity_noops_without_callable_api() -> None:
    """Activity refresh exits when the API client lacks modules_activity."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    assert runtime.supports_module_activity is False
    await runtime.async_refresh_activity("DEV1")
    assert runtime.activity("DEV1") == []


@pytest.mark.asyncio
async def test_load_activity_assets_without_get_i18n(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catalog objects without get_i18n fail closed for activity chrome."""
    catalog = types.SimpleNamespace()
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    assert await runtime.async_get_activity_index_label() is None


@pytest.mark.asyncio
async def test_load_activity_assets_logs_fetch_errors(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Activity asset load failures leave index label unset."""
    catalog = types.SimpleNamespace(get_i18n=AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    with caplog.at_level("DEBUG"):
        assert await runtime.async_get_activity_index_label() is None
        assert "Failed to load activity chrome" in caplog.text


@pytest.mark.asyncio
async def test_async_refresh_alarms_without_api_helpers() -> None:
    """Alarm refresh exits when REST helpers are missing."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    assert runtime.supports_module_alarms is False
    await runtime.async_refresh_alarms("DEV1")
    assert runtime.alarms_current("DEV1") == []


@pytest.mark.asyncio
async def test_normalize_alarm_row_coerces_float_and_string_ids() -> None:
    """Alarm rows coerce numeric ids from float/string sources."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime._alarm_names = {38: "ERROR_X"}
    runtime._errors_i18n = {"ERROR_X": "Fuel missing"}
    row = runtime._normalize_alarm_row(
        {"id": 38.0, "devid": "DEV1", "created_at": "t0", "finished_at": None},
        default_devid="DEV1",
    )
    assert row["id"] == 38
    assert row["name"] == "Fuel missing"
    row2 = runtime._normalize_alarm_row({"id": "54", "devid": "DEV1"}, default_devid="DEV1")
    assert row2["id"] == 54


@pytest.mark.asyncio
async def test_async_refresh_alarms_impl_exits_without_callable_helpers() -> None:
    """Alarm impl returns early when REST helpers are not callable."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    await runtime._async_refresh_alarms_impl("DEV1")
    assert runtime.alarms_current("DEV1") == []


@pytest.mark.asyncio
async def test_normalize_alarm_row_rejects_unrecognized_id() -> None:
    """Alarm rows leave id unset for non-numeric values."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    row = runtime._normalize_alarm_row({"id": "not-a-number", "devid": "DEV1"}, default_devid="DEV1")
    assert row["id"] is None


@pytest.mark.asyncio
async def test_load_alarm_chrome_without_catalog_or_language() -> None:
    """Alarm chrome loading fails closed without catalog or language."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = None
    assert await runtime._load_alarm_chrome_labels() == {}
    runtime.language = "en"
    assert await runtime._load_alarm_chrome_labels() == {}


@pytest.mark.asyncio
async def test_load_alarm_name_maps_without_catalog() -> None:
    """Alarm name maps stay empty when LiveAssetsCatalog is unavailable."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    await runtime._load_alarm_name_maps()
    assert runtime._alarm_names == {}


@pytest.mark.asyncio
async def test_normalize_activity_row_rejects_bool_id() -> None:
    """Activity rows leave id unset for bool values."""
    runtime, *_rest = make_runtime()
    row = await runtime._normalize_activity_row({"id": True}, default_devid="DEV1", resolver=None)
    assert row["id"] is None


@pytest.mark.asyncio
async def test_async_refresh_activity_impl_and_assets_loader() -> None:
    """Activity refresh loads assets and normalizes rows when API support exists."""
    from tests.test_platform_activity import _runtime_with_activity

    runtime, api = _runtime_with_activity()
    await runtime.async_refresh_activity("DEV1")
    assert api.calls == 1
    assert runtime.activity("DEV1")


@pytest.mark.asyncio
async def test_resolve_activity_i18n_swallows_resolver_errors() -> None:
    """Broken resolver hooks return ``None`` instead of raising."""
    resolver = SimpleNamespace(_resolve_i18n_token=AsyncMock(side_effect=RuntimeError("boom")))
    assert await _resolve_activity_i18n_token("token", resolver=resolver) is None


@pytest.mark.asyncio
async def test_resolve_activity_display_value_uses_unit_map_and_i18n() -> None:
    """Activity display values map through unit tables and i18n tokens."""
    resolver = SimpleNamespace(
        resolve_unit=AsyncMock(return_value={"2": "units.two"}),
        _unit_mapping_value_label=lambda _unit, _raw: None,
        _resolve_i18n_token=AsyncMock(return_value="Two"),
    )
    assert await _resolve_activity_display_value(2, unit_code=38, resolver=resolver) == "Two"


@pytest.mark.asyncio
async def test_refresh_route_visibility_skips_unknown_route_match() -> None:
    """Routes missing from the fetched menu do not change visibility state."""
    runtime, *_rest = make_runtime(modules_meta={"dev1": {"device_menu": 0, "permissions": []}})
    runtime.register_route_visibility(
        [
            {
                "devid": "dev1",
                "symbol": "PARAM_177",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "MISSING",
                CONF_ROUTE_VISIBILITY_PATH: "missing",
            }
        ]
    )
    resolver = AsyncMock()
    resolver.get_module_menu = AsyncMock(return_value=SimpleNamespace(routes=[]))
    runtime._status_resolver = resolver
    await runtime.refresh_route_visibility({"PARAM_177"})
    assert runtime.route_visible_for_symbol("dev1", "PARAM_177") is True


@pytest.mark.asyncio
async def test_load_alarm_chrome_and_name_maps(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Alarm chrome/name maps load from catalog when available."""
    catalog = types.SimpleNamespace(
        get_i18n=AsyncMock(
            side_effect=[
                {
                    "currentAlarms": "Current",
                    "historyAlarms": "History",
                    "noAlarms": "None",
                    "noHistory": "No history",
                },
                {"ERROR_X": "Fuel"},
            ]
        ),
        _idx=types.SimpleNamespace(
            find_asset_for_basename=lambda _n: types.SimpleNamespace(url="https://example/a.js"),
            assets_by_basename={"Alarms": [types.SimpleNamespace(url="https://example/a.js")]},
        ),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )

    async def _get_bytes(_url: str) -> bytes:
        return b'38:"ERROR_X"'

    runtime, api, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    api.get_bytes = _get_bytes  # type: ignore[attr-defined, method-assign]

    labels = await runtime._load_alarm_chrome_labels()
    assert labels["currentAlarms"] == "Current"
    await runtime._load_alarm_name_maps()
    assert runtime._errors_i18n.get("ERROR_X") == "Fuel"

    broken = types.SimpleNamespace(get_i18n=AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: broken,
    )
    with caplog.at_level("DEBUG"):
        assert await runtime._load_alarm_chrome_labels() == {}
        assert "Failed to load alarm chrome i18n" in caplog.text


def test_alarm_helper_and_catalog_edge_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alarm helpers and catalog construction tolerate missing library pieces."""
    assert _resolve_alarm_row_name(38, alarm_names={38: "ERROR_X"}, errors_i18n={"ERROR_X": "Fuel"}) == "Fuel"
    assert _try_live_assets_catalog(object()) is None

    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (None, None),
    )
    assert _resolve_alarm_row_name(38, alarm_names={38: "ERROR_X"}, errors_i18n={"ERROR_X": "Fuel"}) == "Fuel"

    def _broken_catalog(_api: object) -> None:
        raise TypeError("stub")

    monkeypatch.setattr(
        "custom_components.habragerone.runtime.LiveAssetsCatalog",
        _broken_catalog,
        raising=False,
    )
    monkeypatch.setitem(
        __import__("sys").modules, "pybragerone.models.catalog", types.SimpleNamespace(LiveAssetsCatalog=_broken_catalog)
    )
    assert _try_live_assets_catalog(object()) is None


@pytest.mark.asyncio
async def test_dispatch_triggers_route_visibility_refresh() -> None:
    """Param updates on route-visibility deps trigger a refresh pass."""
    runtime, *_rest = make_runtime(
        flat_values={"P6.v219": 0},
        modules_meta={"dev1": {"device_menu": 0, "permissions": []}},
    )
    runtime.register_route_visibility(
        [
            {
                "devid": "dev1",
                "symbol": "PARAM_219",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "modules.menu.circulation",
                CONF_ROUTE_VISIBILITY_PATH: "circulation",
                CONF_ROUTE_VISIBILITY_DEPS: ["P6.v219"],
            }
        ]
    )
    route = SimpleNamespace(
        name="modules.menu.circulation",
        path="circulation",
        meta=SimpleNamespace(display_dropdown="P6.v219"),
        children=[],
    )
    resolver = AsyncMock()
    resolver.get_module_menu = AsyncMock(return_value=SimpleNamespace(routes=[route]))
    runtime._status_resolver = resolver

    await runtime.start()
    runtime.gateway.bus.push(FakeParamUpdate(pool="P6", chan="v", idx=219))
    await asyncio.sleep(0.1)
    assert runtime.route_visible_for_symbol("dev1", "PARAM_219") is False
    await runtime.stop()


@pytest.mark.asyncio
async def test_load_alarm_chrome_without_get_i18n(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alarm chrome loading requires a callable catalog ``get_i18n`` hook."""
    catalog = types.SimpleNamespace()
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    assert await runtime._load_alarm_chrome_labels() == {}


@pytest.mark.asyncio
async def test_load_alarm_chrome_rejects_non_mapping_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-mapping alarm i18n payloads fail closed."""
    catalog = types.SimpleNamespace(get_i18n=AsyncMock(return_value="bad"))
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    assert await runtime._load_alarm_chrome_labels() == {}


@pytest.mark.asyncio
async def test_load_alarm_name_maps_logs_fetch_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Alarm name map loading logs and swallows catalog failures."""
    catalog = types.SimpleNamespace(
        get_i18n=AsyncMock(side_effect=RuntimeError("offline")),
        _idx=types.SimpleNamespace(find_asset_for_basename=lambda _n: None, assets_by_basename={}),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    with caplog.at_level("DEBUG"):
        await runtime._load_alarm_name_maps()
        assert "Failed to load AlarmName" in caplog.text


@pytest.mark.asyncio
async def test_async_refresh_activity_impl_without_callable_fn() -> None:
    """Activity impl exits when ``modules_activity`` is not callable."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    await runtime._async_refresh_activity_impl("DEV1")
    assert runtime.activity("DEV1") == []


@pytest.mark.asyncio
async def test_ensure_activity_assets_loads_catalog_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activity asset bootstrap loads routes/state labels from catalog i18n."""
    catalog = types.SimpleNamespace(
        get_i18n=AsyncMock(
            side_effect=[
                {"activity": {"index": " Activity "}},
                {"state": {"success": "Completed"}},
            ]
        )
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    await runtime._ensure_activity_assets()
    assert runtime._activity_index_label == "Activity"
    assert runtime._activity_state_i18n["success"] == "Completed"


@pytest.mark.asyncio
async def test_normalize_activity_row_coerces_float_id_and_rejects_garbage() -> None:
    """Activity ids accept floats and reject unknown shapes."""
    runtime, *_rest = make_runtime()
    row = await runtime._normalize_activity_row({"id": 42.0}, default_devid="DEV1", resolver=None)
    assert row["id"] == 42
    row2 = await runtime._normalize_activity_row({"id": "nope"}, default_devid="DEV1", resolver=None)
    assert row2["id"] is None


@pytest.mark.asyncio
async def test_resolve_activity_display_value_branches() -> None:
    """Display-value helper covers resolver failures and mapping fallbacks."""
    assert await _resolve_activity_display_value(1, unit_code=None, resolver=None) == 1

    resolver = SimpleNamespace(
        resolve_unit=AsyncMock(return_value=None),
        _unit_mapping_value_label=lambda *_a: None,
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=resolver) == 1

    broken_label = SimpleNamespace(
        resolve_unit=AsyncMock(return_value={"1": "units.one"}),
        _unit_mapping_value_label=lambda *_a: (_ for _ in ()).throw(RuntimeError("boom")),
        _resolve_i18n_token=AsyncMock(return_value=None),
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=broken_label) == "units.one"

    mapped = SimpleNamespace(
        resolve_unit=AsyncMock(return_value={"1": "units.one"}),
        _unit_mapping_value_label=lambda *_a: "units.one",
        _resolve_i18n_token=AsyncMock(return_value=None),
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=mapped) == "units.one"


@pytest.mark.asyncio
async def test_load_alarm_chrome_without_language_after_catalog_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank language short-circuits alarm chrome even when catalog exists."""
    catalog = types.SimpleNamespace(get_i18n=AsyncMock())
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "   "
    assert await runtime._load_alarm_chrome_labels() == {}


@pytest.mark.asyncio
async def test_resolve_activity_display_value_more_branches() -> None:
    """Display-value helper handles missing hooks and raw label fallback."""
    resolver = SimpleNamespace(_unit_mapping_value_label=lambda *_a: None)
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=resolver) == 1

    resolver2 = SimpleNamespace(
        resolve_unit=AsyncMock(return_value="not-a-map"),
        _unit_mapping_value_label=lambda *_a: None,
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=resolver2) == 1

    resolver3 = SimpleNamespace(
        resolve_unit=AsyncMock(return_value={"1": "label.key"}),
        _unit_mapping_value_label=lambda *_a: None,
        _resolve_i18n_token=AsyncMock(return_value=None),
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=resolver3) == "label.key"

    resolver4 = SimpleNamespace(
        resolve_unit=AsyncMock(return_value={"other": "x"}),
        _unit_mapping_value_label=lambda *_a: None,
        _resolve_i18n_token=AsyncMock(return_value=None),
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=resolver4) == 1


def test_alarm_name_helpers_missing_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing AlarmName helpers surface as ``(None, None)``."""
    monkeypatch.setattr("custom_components.habragerone.runtime._parse_alarm_name_enum", None)
    monkeypatch.setattr("custom_components.habragerone.runtime._resolve_alarm_label", None)
    assert _alarm_name_helpers() == (None, None)


def test_import_alarm_name_helpers_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """ImportError from older wheels yields ``(None, None)`` without raising."""
    import builtins

    real_import = builtins.__import__

    def _mock_import(name: str, globals: object = None, locals: object = None, fromlist: object = (), level: int = 0) -> object:
        if name == "pybragerone.models.alarm_names":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    assert _import_alarm_name_helpers() == (None, None)


def test_import_alarm_name_helpers_returns_callables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful import binds parse/resolve callables used by the runtime."""
    import types

    fake = types.ModuleType("pybragerone.models.alarm_names")

    def _parse(_source: object) -> dict[int, str]:
        return {38: "ERROR_X"}

    def _resolve(_alarm_id: int, *, alarm_names: object, errors_i18n: object) -> str:
        return "Fuel"

    fake.parse_alarm_name_enum = _parse  # type: ignore[attr-defined]
    fake.resolve_alarm_label = _resolve  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pybragerone.models.alarm_names", fake)

    parse_fn, resolve_fn = _import_alarm_name_helpers()
    assert parse_fn is _parse
    assert resolve_fn is _resolve


def test_try_live_assets_catalog_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing LiveAssetsCatalog import is treated as unavailable."""
    import builtins

    real_import = builtins.__import__

    def _mock_import(name: str, globals: object = None, locals: object = None, fromlist: object = (), level: int = 0) -> object:
        if name == "pybragerone.models.catalog":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    assert _try_live_assets_catalog(object()) is None


def test_alarm_name_helpers_returns_imported_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper accessor returns parse/resolve callables when bound at import time."""

    def _parse(_source: object) -> dict[int, str]:
        return {38: "ERROR_X"}

    def _resolve(_alarm_id: int, *, alarm_names: object, errors_i18n: object) -> str:
        return "Fuel"

    monkeypatch.setattr("custom_components.habragerone.runtime._parse_alarm_name_enum", _parse)
    monkeypatch.setattr("custom_components.habragerone.runtime._resolve_alarm_label", _resolve)
    parse_fn, resolve_fn = _alarm_name_helpers()
    assert callable(parse_fn)
    assert callable(resolve_fn)
    assert _resolve_alarm_row_name(38, alarm_names={38: "ERROR_X"}, errors_i18n={"ERROR_X": "Fuel"}) == "Fuel"


def test_resolve_alarm_row_name_rejects_blank_helper_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank helper labels are treated as unresolved."""

    def _blank(_alarm_id: int, *, alarm_names: object, errors_i18n: object) -> str:
        return "   "

    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (None, _blank),
    )
    assert _resolve_alarm_row_name(38, alarm_names={38: "ERROR_X"}, errors_i18n={"ERROR_X": "Fuel"}) is None


def test_resolve_alarm_row_name_swallows_helper_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve helper exceptions return ``None`` instead of raising."""

    def _boom(_alarm_id: int, *, alarm_names: object, errors_i18n: object) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (None, _boom),
    )
    assert _resolve_alarm_row_name(38, alarm_names={38: "ERROR_X"}, errors_i18n={"ERROR_X": "Fuel"}) is None


@pytest.mark.asyncio
async def test_load_alarm_name_maps_partial_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alarm name loading covers non-callable/empty/non-mapping branches."""
    catalog = types.SimpleNamespace(
        get_i18n="not-callable",
        _idx=types.SimpleNamespace(find_asset_for_basename=lambda _n: None, assets_by_basename={}),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (None, None),
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    await runtime._load_alarm_name_maps()
    assert runtime._alarm_names == {}

    catalog2 = types.SimpleNamespace(
        get_i18n=AsyncMock(return_value="not-a-mapping"),
        fetch_alarm_name_source=AsyncMock(return_value=b"source"),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog2,
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (lambda _src: "not-dict", None),
    )
    runtime2, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime2.language = "en"
    await runtime2._load_alarm_name_maps()
    assert runtime2._alarm_names == {}

    catalog3 = types.SimpleNamespace(
        get_i18n=AsyncMock(return_value={"ERROR_X": "Fuel"}),
        fetch_alarm_name_source=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog3,
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (lambda _src: {38: "ERROR_X"}, None),
    )
    runtime3, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime3.language = "en"
    await runtime3._load_alarm_name_maps()
    assert runtime3._alarm_names == {}

    catalog4 = types.SimpleNamespace(get_i18n=AsyncMock(return_value={}))
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog4,
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._alarm_name_helpers",
        lambda: (lambda _src: {38: "ERROR_X"}, None),
    )
    runtime4, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime4.language = "en"
    await runtime4._load_alarm_name_maps()
    assert runtime4._alarm_names == {}

    catalog5 = types.SimpleNamespace(
        get_i18n=AsyncMock(return_value={}),
        fetch_alarm_name_source=AsyncMock(return_value=b"alarms-chunk"),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog5,
    )
    runtime5, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime5.language = "en"
    await runtime5._load_alarm_name_maps()
    assert runtime5._alarm_names == {38: "ERROR_X"}


@pytest.mark.asyncio
async def test_load_activity_assets_partial_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activity chrome loading covers non-mapping / blank / non-string branches."""
    catalog = types.SimpleNamespace(
        get_i18n=AsyncMock(
            side_effect=[
                "not-a-mapping",
                "also-not-mapping",
            ]
        )
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    await runtime._load_activity_assets()
    assert runtime._activity_index_label is None
    assert runtime._activity_state_i18n == {}

    catalog2 = types.SimpleNamespace(
        get_i18n=AsyncMock(
            side_effect=[
                {"activity": "bad"},
                {"state": "bad"},
            ]
        )
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog2,
    )
    runtime2, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime2.language = "en"
    await runtime2._load_activity_assets()
    assert runtime2._activity_index_label is None

    catalog3 = types.SimpleNamespace(
        get_i18n=AsyncMock(
            side_effect=[
                {"activity": {"index": "   "}},
                {"state": {1: "x", "ok": "  ", "good": "Done"}},
            ]
        )
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog3,
    )
    runtime3, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime3.language = "en"
    await runtime3._load_activity_assets()
    assert runtime3._activity_index_label is None
    assert runtime3._activity_state_i18n == {"good": "Done"}


@pytest.mark.asyncio
async def test_normalize_activity_row_state_label_requires_string() -> None:
    """Non-string state map values leave ``state`` unset."""
    runtime, *_rest = make_runtime()
    runtime._activity_state_i18n = {"ok": 123}  # type: ignore[assignment]
    row = await runtime._normalize_activity_row(
        {"id": 1, "state": "ok"},
        default_devid="DEV1",
        resolver=None,
    )
    assert row["state"] is None


def test_extract_activity_and_alarm_rows_nested_non_list_data() -> None:
    """Nested ``{data: ...}`` payloads require a list data field."""
    assert _extract_activity_rows((200, {"activities": {"data": "bad"}})) == []
    assert _extract_alarm_rows((200, {"alarms": {"data": "bad"}})) == []


def test_activity_row_devid_rejects_non_string_module_devid() -> None:
    """Module objects without a string devid fall back to the default."""
    assert _activity_row_devid({"module": {"devid": 12}}, default_devid="DEV1") == "DEV1"


def test_activity_value_scalar_nested_none_continues() -> None:
    """Nested maps without a scalar keep searching then return None."""
    assert _activity_value_scalar({"a": {"b": {}}, "c": {"d": None}}) is None


@pytest.mark.asyncio
async def test_resolve_activity_display_value_without_mapping_label_hook() -> None:
    """Missing ``_unit_mapping_value_label`` falls through to unit table lookup."""
    resolver = SimpleNamespace(
        resolve_unit=AsyncMock(return_value={"1": "units.one"}),
        _resolve_i18n_token=AsyncMock(return_value=None),
    )
    assert await _resolve_activity_display_value(1, unit_code=1, resolver=resolver) == "units.one"


def test_module_events_rest_ok() -> None:
    """REST tuple guard accepts only 200/204 success tuples with app-level status."""
    assert _module_events_rest_ok((200, {"alarms": []})) is True
    assert _module_events_rest_ok((200, {"status": True, "alarms": []})) is True
    assert _module_events_rest_ok((200, {"status": False, "alarms": []})) is False
    assert _module_events_rest_ok((200, {"status": False, "activities": []})) is False
    assert _module_events_rest_ok((200,)) is True
    assert _module_events_rest_ok((204,)) is True
    assert _module_events_rest_ok((204, None)) is True
    assert _module_events_rest_ok((401, {})) is False
    assert _module_events_rest_ok(()) is False
    assert _module_events_rest_ok("not-a-tuple") is False


@pytest.mark.asyncio
async def test_ensure_alarm_name_maps_retries_until_both_maps_loaded() -> None:
    """Alarm name assets stay reloadable until both enum and errors maps populate."""
    runtime, *_rest = make_runtime()
    runtime.language = "en"
    calls = 0

    async def _load(_self: BragerRuntime) -> None:
        nonlocal calls
        calls += 1
        _self._errors_i18n = {"ERROR_X": "Fuel"}
        _self._alarm_names = {38: "ERROR_X"} if calls > 1 else {}

    with patch.object(BragerRuntime, "_load_alarm_name_maps", _load):
        await runtime._ensure_alarm_name_maps()
        assert calls == 1
        assert runtime._alarm_names_loaded is False
        await runtime._ensure_alarm_name_maps()
        assert calls == 2
        assert runtime._alarm_names_loaded is True


@pytest.mark.asyncio
async def test_stop_cancels_background_refresh_tasks() -> None:
    """Background refresh tasks are cancelled during runtime shutdown."""
    runtime, *_rest = make_runtime()
    task = asyncio.create_task(asyncio.sleep(3600), name="habragerone-activity-after-write-DEV1")
    runtime._background_tasks.add(task)
    task.add_done_callback(runtime._background_tasks.discard)

    await runtime.stop()

    assert task.cancelled()
    assert not runtime._background_tasks


@pytest.mark.asyncio
async def test_stop_cancels_inflight_alarm_and_activity_refresh_tasks() -> None:
    """In-flight alarm/activity refresh tasks are cancelled during shutdown."""
    runtime, *_rest = make_runtime()
    alarm_task = asyncio.create_task(asyncio.sleep(3600), name="habragerone-alarms-DEV1")
    activity_task = asyncio.create_task(asyncio.sleep(3600), name="habragerone-activity-DEV1")
    runtime._alarms_refresh_tasks["DEV1"] = alarm_task
    runtime._activity_refresh_tasks["DEV1"] = activity_task

    await runtime.stop()

    assert alarm_task.cancelled()
    assert activity_task.cancelled()
    assert not runtime._alarms_refresh_tasks
    assert not runtime._activity_refresh_tasks


@pytest.mark.asyncio
async def test_async_refresh_alarms_task_ownership_race() -> None:
    """Finally cleanup skips popping when another task replaced the slot."""
    from tests.test_platform_alarms import _AlarmsApi

    api = _AlarmsApi()
    runtime, *_rest = make_runtime(api=api, modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    runtime._alarm_names_loaded = True

    original_impl = BragerRuntime._async_refresh_alarms_impl

    async def _hijack(self: BragerRuntime, devid_key: str) -> None:
        runtime._alarms_refresh_tasks[devid_key] = asyncio.create_task(asyncio.sleep(0))
        await original_impl(self, devid_key)

    with patch.object(BragerRuntime, "_async_refresh_alarms_impl", _hijack):
        await runtime.async_refresh_alarms("DEV1")


@pytest.mark.asyncio
async def test_async_refresh_activity_task_ownership_race() -> None:
    """Activity finally cleanup skips popping when another task owns the slot."""
    from tests.test_platform_activity import _ActivityApi

    api = _ActivityApi()
    runtime, *_rest = make_runtime(api=api, modules_meta={"DEV1": {"name": "Boiler"}})
    runtime._activity_assets_loaded = True
    runtime._activity_index_label = "Activity"

    original_impl = BragerRuntime._async_refresh_activity_impl

    async def _hijack(self: BragerRuntime, devid_key: str) -> None:
        runtime._activity_refresh_tasks[devid_key] = asyncio.create_task(asyncio.sleep(0))
        await original_impl(self, devid_key)

    with patch.object(BragerRuntime, "_async_refresh_activity_impl", _hijack):
        await runtime.async_refresh_activity("DEV1")


@pytest.mark.asyncio
async def test_on_gateway_alarm_quantity_schedules_refresh() -> None:
    """Alarm quantity push events schedule async_refresh_alarms for the devid."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    scheduled: list[str] = []

    async def _refresh(_self: BragerRuntime, devid: str) -> None:
        scheduled.append(devid)

    with patch.object(BragerRuntime, "async_refresh_alarms", _refresh):
        runtime._on_gateway_alarm_quantity(types.SimpleNamespace(devid="DEV1", changed=True))
        await asyncio.sleep(0)
        assert scheduled == ["DEV1"]

        scheduled.clear()
        runtime._on_gateway_alarm_quantity(types.SimpleNamespace(devid="DEV1", changed=False))
        await asyncio.sleep(0)
        assert scheduled == []


def test_on_gateway_alarm_quantity_ignores_blank_devid() -> None:
    """Blank devid must not schedule alarm refresh work."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})

    with patch.object(BragerRuntime, "async_refresh_alarms", AsyncMock()) as refresh:
        runtime._on_gateway_alarm_quantity(types.SimpleNamespace(devid="   ", changed=True))
        refresh.assert_not_called()


def test_on_gateway_alarm_quantity_requires_running_loop() -> None:
    """Without a running event loop the callback must not spawn background work."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})

    with (
        patch.object(asyncio, "get_running_loop", side_effect=RuntimeError),
        patch.object(BragerRuntime, "async_refresh_alarms", AsyncMock()) as refresh,
    ):
        runtime._on_gateway_alarm_quantity(types.SimpleNamespace(devid="DEV1", changed=True))
        refresh.assert_not_called()
