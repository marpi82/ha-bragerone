"""Tests for module activity feed sensors (#223)."""

from __future__ import annotations

import asyncio
import types
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import (  # noqa: E402
    CONF_MODULES_META,
    DATA_ENTITY_STATS,
    DOMAIN,
)
from custom_components.habragerone.event_feeds import (  # noqa: E402
    BragerActivitySensor,
    iter_activity_feed_entities,
)
from custom_components.habragerone.runtime import (  # noqa: E402
    _activity_row_devid,
    _activity_value_scalar,
    _extract_activity_rows,
)
from custom_components.habragerone.sensor import async_setup_entry  # noqa: E402
from tests.helpers.descriptors import sensor_descriptor  # noqa: E402
from tests.helpers.fakes import FakeApi, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


class _ActivityApi(FakeApi):
    """Fake API with modules_activity list helper."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.payload: dict[str, Any] = {
            "status": True,
            "activities": {
                "data": [
                    {
                        "id": 610249,
                        "devid": "DEV1",
                        "name": "parameters.PARAM_219",
                        "unit": 12,
                        "value": 0,
                        "prevValue": 2,
                        "state": "success",
                        "created_at": "2026-08-19T18:39:24.000+00:00",
                        "user": "marpi82",
                    }
                ]
            },
        }

    async def modules_activity(
        self,
        modules: list[str],
        *,
        page: int = 1,
        limit: int = 20,
        return_data: bool = False,
    ) -> tuple[int, Any] | bool:
        self.calls += 1
        assert modules == ["DEV1"]
        assert page == 1
        assert limit == 20
        return (200, self.payload) if return_data else True


def _runtime_with_activity(*, language: str = "en") -> tuple[Any, _ActivityApi]:
    api = _ActivityApi()
    runtime, *_rest = make_runtime(api=api, modules_meta={"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}})
    runtime.language = language
    runtime._activity_index_label = "Activity"
    runtime._activity_state_i18n = {"success": "Completed"}
    runtime._activity_assets_loaded = True
    return runtime, api


@pytest.mark.asyncio
async def test_async_refresh_activity_normalizes_rows() -> None:
    runtime, api = _runtime_with_activity()
    seen: list[str] = []
    runtime.add_event_feed_listener(seen.append)

    await runtime.async_refresh_activity("DEV1")

    assert api.calls == 1
    assert seen == ["DEV1"]
    rows = runtime.activity("DEV1")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == 610249
    assert row["devid"] == "DEV1"
    assert row["parameter_key"] == "parameters.PARAM_219"
    assert row["value_raw"] == 0
    assert row["prev_value_raw"] == 2
    assert row["state_key"] == "success"
    assert row["state"] == "Completed"
    assert row["created_at"] == "2026-08-19T18:39:24.000+00:00"
    assert row["created_by"] == "marpi82"


@pytest.mark.asyncio
async def test_async_refresh_activity_noops_without_api() -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    await runtime.async_refresh_activity("DEV1")
    assert runtime.activity("DEV1") == []
    assert runtime.supports_module_activity is False


@pytest.mark.asyncio
async def test_iter_activity_feed_entities_fail_closed_without_label(hass: HomeAssistant) -> None:
    runtime, api = _runtime_with_activity()
    runtime._activity_index_label = None
    runtime._activity_assets_loaded = True
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_MODULES_META: {"DEV1": {"name": "Boiler"}}},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    entities = await iter_activity_feed_entities(hass, entry, runtime)
    assert entities == []
    assert api.calls == 0


@pytest.mark.asyncio
async def test_iter_and_setup_create_activity_sensor(hass: HomeAssistant) -> None:
    runtime, api = _runtime_with_activity()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[sensor_descriptor()])
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_MODULES_META: {"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}},
        },
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)

    activity = [entity for entity in added if isinstance(entity, BragerActivitySensor)]
    assert len(activity) == 1
    assert api.calls == 1

    entity = activity[0]
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert entity._attr_should_poll is False
    assert entity._attr_has_entity_name is True
    assert entity._attr_name == "Activity"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_activity"
    assert entity._attr_native_value == 1
    attrs = entity.extra_state_attributes
    assert attrs["activities"][0]["id"] == 610249
    assert attrs["activities"][0]["parameter_key"] == "parameters.PARAM_219"
    assert attrs["activities"][0]["state"] == "Completed"
    assert attrs["activities"][0]["created_by"] == "marpi82"

    info = entity.device_info
    assert info is not None
    assert (DOMAIN, "DEV1") in info["identifiers"]
    assert info.get("manufacturer") == "BragerOne"

    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["sensor"]
    # 1 descriptor sensor + 1 activity (alarms skipped: no modules_alarms on API)
    assert stats["created_count"] == 2
    assert stats["descriptor_count"] == 2


@pytest.mark.asyncio
async def test_activity_sensor_refreshes_when_module_comes_online(hass: HomeAssistant) -> None:
    runtime, api = _runtime_with_activity()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerActivitySensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta={"name": "Boiler"},
        name="Activity",
    )
    entity.hass = hass
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    assert api.calls == 0

    api.payload = {
        "status": True,
        "activities": {
            "data": [
                {"id": 1, "devid": "DEV1", "name": "parameters.PARAM_1", "value": 1, "state": "success"},
                {"id": 2, "devid": "DEV1", "name": "parameters.PARAM_2", "value": 2, "state": "success"},
            ]
        },
    }
    runtime._module_online["DEV1"] = False
    entity._on_connectivity("DEV1", True, True)
    await hass.async_block_till_done()
    await entity.async_update()
    assert api.calls >= 1
    assert entity._attr_native_value == 2

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_feed is None
    assert entity._unsubscribe_connectivity is None


@pytest.mark.asyncio
async def test_activity_sensor_event_feed_updates_state(hass: HomeAssistant) -> None:
    runtime, _api = _runtime_with_activity()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerActivitySensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta={"name": "Boiler"},
        name="Activity",
    )
    entity.hass = hass
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    runtime._activity["DEV1"] = [
        {"id": 1, "devid": "DEV1", "parameter_key": "parameters.PARAM_1"},
        {"id": 2, "devid": "DEV1", "parameter_key": "parameters.PARAM_2"},
        {"id": 3, "devid": "DEV1", "parameter_key": "parameters.PARAM_3"},
    ]
    entity._on_event_feed("DEV1")
    assert entity._attr_native_value == 3
    entity._on_event_feed("OTHER")
    assert entity._attr_native_value == 3


def test_extract_activity_rows_handles_list_and_nested_shapes() -> None:
    """REST payloads may expose activities as a list or ``{data: [...]}`` mapping."""
    list_payload = (200, {"activities": [{"id": 1}]})
    nested_payload = (200, {"activities": {"data": [{"id": 2}]}})
    assert _extract_activity_rows(list_payload) == [{"id": 1}]
    assert _extract_activity_rows(nested_payload) == [{"id": 2}]
    assert _extract_activity_rows((200, {"activities": "bad"})) == []


@pytest.mark.asyncio
async def test_async_refresh_activity_dedupes_concurrent_tasks() -> None:
    """Parallel refreshes for one devid share a single in-flight task."""
    runtime, api = _runtime_with_activity()

    async def slow_activity(*_args: Any, **kwargs: Any) -> tuple[int, Any] | bool:
        await asyncio.sleep(0.05)
        api.calls += 1
        return (200, api.payload) if kwargs.get("return_data") else True

    api.modules_activity = slow_activity  # type: ignore[method-assign]
    await asyncio.gather(runtime.async_refresh_activity("DEV1"), runtime.async_refresh_activity("DEV1"))
    assert api.calls == 1


@pytest.mark.asyncio
async def test_iter_activity_feed_entities_fail_closed_without_api(hass: HomeAssistant) -> None:
    """No entities when the API client lacks activity helpers."""
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_MODULES_META: {"DEV1": {"name": "Boiler"}}},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry
    assert await iter_activity_feed_entities(hass, entry, runtime) == []


@pytest.mark.asyncio
async def test_async_get_activity_index_label_loads_from_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activity index label is fetched from routes + i18n when not cached."""
    catalog = types.SimpleNamespace(
        refresh_index=AsyncMock(),
        get_i18n=AsyncMock(
            side_effect=[
                {"activity": {"index": " Activity "}},
                {"state": {"success": "Completed"}},
            ]
        ),
    )
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    assert await runtime.async_get_activity_index_label() == "Activity"


@pytest.mark.asyncio
async def test_async_get_activity_index_label_skips_broken_refresh_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: activity chrome must load even when refresh_index() would fail."""

    async def _broken_refresh_index() -> None:
        msg = "refresh_index() missing 1 required positional argument: 'index_url'"
        raise TypeError(msg)

    get_i18n = AsyncMock(
        side_effect=[
            {"activity": {"index": " Activity "}},
            {"state": {"success": "Completed"}},
        ]
    )
    catalog = types.SimpleNamespace(refresh_index=_broken_refresh_index, get_i18n=get_i18n)
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = "en"
    assert await runtime.async_get_activity_index_label() == "Activity"
    assert get_i18n.await_count == 2


def test_activity_row_devid_and_value_scalar_helpers() -> None:
    """Row devid falls back to module.devid; nested value maps unwrap."""
    assert _activity_row_devid({"module": {"devid": "M1"}}, default_devid="DEV1") == "M1"
    assert _activity_row_devid({}, default_devid="DEV1") == "DEV1"
    assert _activity_value_scalar({"value": {"prevValue": 3}}) == 3
    assert _activity_value_scalar({"other": 1}) is None


@pytest.mark.asyncio
async def test_async_refresh_activity_noops_on_blank_devid() -> None:
    """Whitespace devids are ignored."""
    runtime, api = _runtime_with_activity()
    await runtime.async_refresh_activity("  ")
    assert api.calls == 0


@pytest.mark.asyncio
async def test_async_refresh_activity_logs_api_failures() -> None:
    """REST failures are logged and leave caches empty."""
    runtime, api = _runtime_with_activity()

    async def boom(*_a: object, **_k: object) -> tuple[int, Any]:
        raise RuntimeError("network down")

    api.modules_activity = boom  # type: ignore[method-assign]
    await runtime.async_refresh_activity("DEV1")
    assert runtime.activity("DEV1") == []


@pytest.mark.asyncio
async def test_load_activity_assets_fail_closed_without_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing language prevents activity chrome from loading."""
    catalog = types.SimpleNamespace(refresh_index=AsyncMock(), get_i18n=AsyncMock())
    monkeypatch.setattr(
        "custom_components.habragerone.runtime._try_live_assets_catalog",
        lambda _api: catalog,
    )
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.language = None
    assert await runtime.async_get_activity_index_label() is None
    catalog.get_i18n.assert_not_called()


@pytest.mark.asyncio
async def test_iter_activity_feed_entities_skips_blank_devids(hass: HomeAssistant) -> None:
    """Blank module keys in modules_meta are ignored."""
    runtime, api = _runtime_with_activity()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_MODULES_META: {"": {"name": "Empty"}, "DEV1": {"name": "Boiler"}}},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry
    entities = await iter_activity_feed_entities(hass, entry, runtime)
    assert len(entities) == 1
    assert api.calls == 1
