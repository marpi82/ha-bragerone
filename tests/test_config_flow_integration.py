"""Integration tests for Brager config/options/reauth flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pybragerone.api.client import ApiError
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockModule, mock_integration, mock_platform

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

import custom_components.habragerone.config_flow as config_flow_module  # noqa: E402
from custom_components.habragerone.const import (  # noqa: E402
    CONF_BACKEND_PLATFORM,
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENTITY_FILTER_MODE,
    CONF_LANGUAGE,
    CONF_MODULES,
    CONF_OBJECT_ID,
    DOMAIN,
    FILTER_MODE_UI,
)
from tests.helpers.config_flow import make_fake_api, patch_config_flow_dependencies  # noqa: E402

_USER_INPUT = {
    CONF_EMAIL: "user@example.com",
    CONF_PASSWORD: "secret",
    CONF_BACKEND_PLATFORM: "bragerone",
    CONF_LANGUAGE: "en",
}


@pytest.fixture(autouse=True)
def register_config_flow_platform(hass: HomeAssistant) -> None:
    """Register the custom integration config flow handler with hass."""
    mock_integration(hass, MockModule(DOMAIN), built_in=False)
    mock_platform(hass, f"{DOMAIN}.config_flow", config_flow_module, built_in=False)


from custom_components.habragerone.const import (  # noqa: E402
    CONF_BACKEND_PLATFORM,
    CONF_LANGUAGE,
)

_USER_INPUT = {
    CONF_EMAIL: "user@example.com",
    CONF_PASSWORD: "secret",
    CONF_BACKEND_PLATFORM: "bragerone",
    CONF_LANGUAGE: "en",
}


@pytest.mark.asyncio
async def test_config_flow_user_step_shows_form(hass: HomeAssistant) -> None:
    with patch_config_flow_dependencies():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_config_flow_user_step_rejects_auth_error(hass: HomeAssistant) -> None:
    api = make_fake_api(auth_error=True)
    with patch_config_flow_dependencies(api=api):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_USER_INPUT,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "auth"}


@pytest.mark.asyncio
async def test_config_flow_user_step_rejects_invalid_language(hass: HomeAssistant) -> None:
    with patch_config_flow_dependencies():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={**_USER_INPUT, CONF_LANGUAGE: "xx"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_response"}


@pytest.mark.asyncio
async def test_config_flow_happy_path_creates_entry(hass: HomeAssistant) -> None:
    with patch_config_flow_dependencies() as (api, bootstrap_mock):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_USER_INPUT,
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_site"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OBJECT_ID: 1})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_modules"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_MODULES: ["DEV1"], CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com (bragerone, id=1)"
    assert result["data"][CONF_EMAIL] == "user@example.com"
    assert result["data"][CONF_OBJECT_ID] == 1
    assert result["data"][CONF_MODULES] == ["DEV1"]
    assert result["data"][CONF_ENTITY_DESCRIPTORS]
    api.ensure_auth.assert_awaited()
    bootstrap_mock.assert_awaited()


@pytest.mark.asyncio
async def test_config_flow_select_modules_rejects_invalid_filter_mode(hass: HomeAssistant) -> None:
    with patch_config_flow_dependencies():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_USER_INPUT,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OBJECT_ID: 1})
        with pytest.raises(InvalidData, match="Schema validation failed"):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_MODULES: ["DEV1"], CONF_ENTITY_FILTER_MODE: "bad-mode"},
            )


@pytest.mark.asyncio
async def test_config_flow_select_modules_handles_bootstrap_failure(hass: HomeAssistant) -> None:
    with patch_config_flow_dependencies(bootstrap_error=RuntimeError("bootstrap failed")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_USER_INPUT,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OBJECT_ID: 1})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_MODULES: ["DEV1"], CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_modules"
    assert result["errors"] == {"base": "invalid_response"}


@pytest.mark.asyncio
async def test_config_flow_reauth_updates_credentials(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old-secret",
            CONF_BACKEND_PLATFORM: "bragerone",
            CONF_OBJECT_ID: 1,
            CONF_MODULES: ["DEV1"],
        },
    )
    entry.add_to_hass(hass)

    with patch_config_flow_dependencies():
        result = await entry.start_reauth_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "new-secret"},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"


@pytest.mark.asyncio
async def test_config_flow_reauth_shows_auth_error(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old-secret",
            CONF_BACKEND_PLATFORM: "bragerone",
            CONF_OBJECT_ID: 1,
            CONF_MODULES: ["DEV1"],
        },
    )
    entry.add_to_hass(hass)

    api = make_fake_api(auth_error=True)
    with patch_config_flow_dependencies(api=api):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "bad-secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "auth"}


@pytest.mark.asyncio
async def test_options_flow_updates_module_scope(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_BACKEND_PLATFORM: "bragerone",
            CONF_OBJECT_ID: 1,
            CONF_MODULES: ["DEV1"],
            CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI,
        },
    )
    entry.add_to_hass(hass)

    with patch_config_flow_dependencies():
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_OBJECT_ID: 1})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "modules"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_MODULES: ["DEV1"], CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_OBJECT_ID] == 1
    assert result["data"][CONF_MODULES] == ["DEV1"]


@pytest.mark.asyncio
async def test_options_flow_aborts_when_no_objects(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_BACKEND_PLATFORM: "bragerone",
            CONF_OBJECT_ID: 1,
            CONF_MODULES: ["DEV1"],
        },
    )
    entry.add_to_hass(hass)

    api = make_fake_api(objects=[])
    with patch_config_flow_dependencies(api=api):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_response"


@pytest.mark.asyncio
async def test_config_flow_select_site_handles_module_api_error(hass: HomeAssistant) -> None:
    api = make_fake_api()
    api.get_modules = AsyncMock(side_effect=ApiError(503, {"message": "down"}))

    with patch_config_flow_dependencies(api=api):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_USER_INPUT,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_OBJECT_ID: 1})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_site"
    assert result["errors"] == {"base": "cannot_connect"}
