"""Config flow for BragerOne Home Assistant integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from pybragerone import BragerOneApiClient
from pybragerone.api.client import ApiError

from .bootstrap import async_build_bootstrap_payload
from .const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_MODULES,
    CONF_MODULES_META,
    CONF_OBJECT_ID,
    DOMAIN,
)


def _module_choices(modules: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Build module code choices as ``(value, label)`` list."""
    choices: list[tuple[str, str]] = []
    for module in modules:
        code = str(module.get("devid", "")).strip()
        if not code:
            continue
        name = str(module.get("name") or module.get("moduleTitle") or "Module")
        version = str(module.get("moduleVersion") or "-")
        choices.append((code, f"{name} (devid={code}, version={version})"))
    return choices


class BragerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Login + installation/module selection flow."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize temporary flow state."""
        self._email: str | None = None
        self._password: str | None = None
        self._object_choices: list[tuple[int, str]] = []
        self._api: BragerOneApiClient | None = None

    async def _api_client(self) -> BragerOneApiClient:
        if self._api is None:
            self._api = BragerOneApiClient()
        return self._api

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect credentials and authenticate."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
            )

        email = str(user_input[CONF_EMAIL]).strip()
        password = str(user_input[CONF_PASSWORD])

        api = await self._api_client()
        try:
            await api.ensure_auth(email, password)
            objects = await api.get_objects()
        except ApiError:
            return self.async_show_form(
                step_id="user",
                errors={"base": "auth"},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL, default=email): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
            )

        self._email = email
        self._password = password
        self._object_choices = [(obj.id, f"{obj.name} (id={obj.id})") for obj in objects]

        if not self._object_choices:
            return self.async_abort(reason="invalid_response")

        return await self.async_step_select_site()

    async def async_step_select_site(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect object and module scope for this entry."""
        if self._email is None or self._password is None:
            return await self.async_step_user()

        object_values = {object_id: label for object_id, label in self._object_choices}
        default_object_id = self._object_choices[0][0]

        if user_input is None:
            return self.async_show_form(
                step_id="select_site",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OBJECT_ID, default=default_object_id): vol.In(object_values),
                        vol.Optional(CONF_MODULES): str,
                    }
                ),
            )

        selected_object_id = int(user_input[CONF_OBJECT_ID])
        modules_csv = str(user_input.get(CONF_MODULES) or "").strip()

        api = await self._api_client()
        try:
            modules = await api.get_modules(selected_object_id)
        except ApiError:
            return self.async_show_form(
                step_id="select_site",
                errors={"base": "cannot_connect"},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OBJECT_ID, default=selected_object_id): vol.In(object_values),
                        vol.Optional(CONF_MODULES): str,
                    }
                ),
            )

        available_codes = {choice for choice, _ in _module_choices([m.model_dump(mode="json") for m in modules])}
        if modules_csv:
            selected_modules = [module.strip() for module in modules_csv.split(",") if module.strip()]
        else:
            selected_modules = sorted(available_codes)

        unknown = [module for module in selected_modules if module not in available_codes]
        if unknown:
            return self.async_show_form(
                step_id="select_site",
                errors={"base": "invalid_response"},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OBJECT_ID, default=selected_object_id): vol.In(object_values),
                        vol.Optional(
                            CONF_MODULES,
                            description={"suggested_value": ",".join(sorted(available_codes))},
                        ): str,
                    }
                ),
                description_placeholders={"modules": ", ".join(sorted(available_codes))},
            )

        await self.async_set_unique_id(f"{self._email}:{selected_object_id}")
        self._abort_if_unique_id_configured()

        bootstrap = await async_build_bootstrap_payload(
            api=api,
            object_id=selected_object_id,
            modules=selected_modules,
        )

        data = {
            CONF_EMAIL: self._email,
            CONF_PASSWORD: self._password,
            CONF_OBJECT_ID: selected_object_id,
            CONF_MODULES: selected_modules,
            CONF_ENTITY_DESCRIPTORS: bootstrap[CONF_ENTITY_DESCRIPTORS],
            CONF_MODULES_META: bootstrap[CONF_MODULES_META],
        }

        return self.async_create_entry(title=f"{self._email} (id={selected_object_id})", data=data)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start re-authentication flow."""
        self._email = str(entry_data.get(CONF_EMAIL, ""))
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Re-authenticate and update credentials."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL, default=self._email or ""): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
            )

        email = str(user_input[CONF_EMAIL]).strip()
        password = str(user_input[CONF_PASSWORD])

        api = await self._api_client()
        try:
            await api.ensure_auth(email, password)
        except ApiError:
            return self.async_show_form(
                step_id="reauth_confirm",
                errors={"base": "auth"},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL, default=email): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
            )

        if self.source != config_entries.SOURCE_REAUTH:
            return self.async_abort(reason="unknown")

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        new_data = dict(entry.data)
        new_data[CONF_EMAIL] = email
        new_data[CONF_PASSWORD] = password
        self.hass.config_entries.async_update_entry(entry, data=new_data)
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return options flow handler."""
        return BragerOptionsFlow(config_entry)


class BragerOptionsFlow(config_entries.OptionsFlow):
    """Options flow for changing object/modules scope."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the config entry reference used by options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Render and handle options form."""
        if user_input is not None:
            modules_csv = str(user_input.get(CONF_MODULES, "")).strip()
            modules = [module.strip() for module in modules_csv.split(",") if module.strip()]
            return self.async_create_entry(
                title="",
                data={
                    CONF_OBJECT_ID: int(user_input[CONF_OBJECT_ID]),
                    CONF_MODULES: modules,
                },
            )

        default_object = int(self.config_entry.data.get(CONF_OBJECT_ID, 0))
        current_modules = self.config_entry.data.get(CONF_MODULES, [])
        modules_csv = ",".join(current_modules) if isinstance(current_modules, list) else ""

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_OBJECT_ID, default=default_object): int,
                    vol.Optional(CONF_MODULES, default=modules_csv): str,
                }
            ),
        )
