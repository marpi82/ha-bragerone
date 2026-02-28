"""Config flow for BragerOne Home Assistant integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from pybragerone import BragerOneApiClient
from pybragerone.api.client import ApiError
from pybragerone.api.server import Platform, server_for
from pybragerone.models.catalog import LiveAssetsCatalog

from .bootstrap import async_build_bootstrap_payload
from .const import (
    CONF_BACKEND_PLATFORM,
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENTITY_FILTER_MODE,
    CONF_LANGUAGE,
    CONF_MODULE_FILTER_MODES,
    CONF_MODULES,
    CONF_MODULES_META,
    CONF_OBJECT_ID,
    DEFAULT_ENTITY_FILTER_MODE,
    DOMAIN,
    FILTER_MODE_PERMISSIONS,
    FILTER_MODE_UI,
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


def _entity_filter_mode_values() -> dict[str, str]:
    return {
        FILTER_MODE_UI: "UI menu filtering",
        FILTER_MODE_PERMISSIONS: "Permission filtering",
    }


def _module_filter_mode_field(module_id: str) -> str:
    return f"{CONF_ENTITY_FILTER_MODE}__{module_id}"


def _extract_selected_module_filter_modes(
    *,
    user_input: dict[str, Any],
    module_ids: list[str],
    default_mode: str,
) -> dict[str, str] | None:
    values = _entity_filter_mode_values()
    selected: dict[str, str] = {}
    for module_id in module_ids:
        field = _module_filter_mode_field(module_id)
        mode = str(user_input.get(field, default_mode)).strip().lower()
        if mode not in values:
            return None
        selected[module_id] = mode
    return selected


def _build_modules_step_schema(
    *,
    module_choices: list[tuple[str, str]],
    module_values: dict[str, str],
    default_modules: list[str],
    module_filter_defaults: dict[str, str],
    filter_values: dict[str, str],
) -> vol.Schema:
    data_schema: dict[Any, Any] = {
        vol.Required(CONF_MODULES, default=default_modules): cv.multi_select(module_values),
    }
    for module_id, _ in module_choices:
        field = vol.Required(
            _module_filter_mode_field(module_id),
            default=module_filter_defaults[module_id],
        )
        data_schema[field] = vol.In(filter_values)
    return vol.Schema(data_schema)


def _extract_language_label(value: Any, *, lang_id: str) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        preferred = value.get(lang_id) or value.get(lang_id.lower()) or value.get(lang_id.upper())
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        for candidate in value.values():
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _looks_like_language_code_label(label: str, *, lang_id: str) -> bool:
    text = " ".join(label.strip().split())
    if not text:
        return True

    lang = lang_id.strip().lower()
    text_lower = text.lower()
    compact = text_lower.replace("-", " ").replace("_", " ")
    parts = [part for part in compact.split(" ") if part]

    if text_lower in {lang, lang.upper(), lang.capitalize()}:
        return True
    return len(parts) == 2 and parts[0] == lang and len(parts[1]) == 2


def _language_label_from_row(row: dict[str, Any], *, lang_id: str) -> str:
    candidates = [
        row.get("nativeName"),
        row.get("autonym"),
        row.get("displayName"),
        row.get("localName"),
        row.get("name"),
        row.get("title"),
        row.get("label"),
    ]
    labels = [label for candidate in candidates if (label := _extract_language_label(candidate, lang_id=lang_id))]
    for label in labels:
        if not _looks_like_language_code_label(label, lang_id=lang_id):
            return label
    if labels:
        return labels[0]
    return lang_id.upper()


class BragerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Login + installation/module selection flow."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize temporary flow state."""
        self._email: str | None = None
        self._password: str | None = None
        self._platform: str = Platform.BRAGERONE.value
        self._language: str | None = None
        self._entity_filter_mode: str = DEFAULT_ENTITY_FILTER_MODE
        self._module_filter_modes: dict[str, str] = {}
        self._object_choices: list[tuple[int, str]] = []
        self._module_choices: list[tuple[str, str]] = []
        self._selected_object_id: int | None = None
        self._api: BragerOneApiClient | None = None
        self._language_cache: dict[str, dict[str, str]] = {}

    async def _api_client(self) -> BragerOneApiClient:
        if self._api is not None:
            return self._api

        self._api = BragerOneApiClient(server=server_for(self._platform))
        return self._api

    async def _reset_api_client(self) -> None:
        if self._api is not None:
            await self._api.close()
            self._api = None

    @staticmethod
    def _platform_values() -> dict[str, str]:
        return {
            Platform.BRAGERONE.value: "BragerOne",
            Platform.TISCONNECT.value: "TisConnect",
        }

    async def _language_values(self, platform: str) -> dict[str, str]:
        cached = self._language_cache.get(platform)
        if cached is not None:
            return cached

        values: dict[str, str] = {}
        api = BragerOneApiClient(server=server_for(platform))
        try:
            cfg = await LiveAssetsCatalog(api).list_language_config()
        except Exception:
            cfg = None
        finally:
            await api.close()

        if cfg is not None:
            for row in cfg.translations:
                lang_id = str(row.get("id") or "").strip().lower()
                if not lang_id or lang_id == "dev":
                    continue
                label_base = _language_label_from_row(row, lang_id=lang_id)
                flag = row.get("flag")
                if isinstance(flag, str) and flag.strip():
                    values[lang_id] = f"{flag} {label_base}"
                else:
                    values[lang_id] = label_base

            default_lang = str(cfg.default_translation).strip().lower()
            if default_lang and default_lang in values:
                ordered = {default_lang: values[default_lang]}
                for key, value in values.items():
                    if key != default_lang:
                        ordered[key] = value
                values = ordered

        if not values:
            values = {"en": "English", "pl": "Polski"}

        self._language_cache[platform] = values
        return values

    async def _user_form_schema(
        self,
        *,
        default_email: str | None = None,
        default_platform: str | None = None,
        default_language: str | None = None,
    ) -> vol.Schema:
        platform = (default_platform or self._platform or Platform.BRAGERONE.value).strip().lower()
        platform_values = self._platform_values()
        if platform not in platform_values:
            platform = Platform.BRAGERONE.value

        language_values = await self._language_values(platform)
        language_default = (default_language or self._language or "").strip().lower()
        if language_default not in language_values:
            language_default = next(iter(language_values.keys()))

        email_default = (default_email or self._email or "").strip()
        schema: dict[Any, Any] = {
            vol.Required(CONF_EMAIL, default=email_default): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_BACKEND_PLATFORM, default=platform): vol.In(platform_values),
            vol.Required(CONF_LANGUAGE, default=language_default): vol.In(language_values),
        }
        return vol.Schema(schema)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect credentials and authenticate."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=await self._user_form_schema(),
            )

        email = str(user_input[CONF_EMAIL]).strip()
        password = str(user_input[CONF_PASSWORD])
        selected_platform = str(user_input.get(CONF_BACKEND_PLATFORM, Platform.BRAGERONE.value)).strip().lower()
        selected_language = str(user_input.get(CONF_LANGUAGE, "")).strip().lower()

        if selected_platform != self._platform:
            self._platform = selected_platform
            await self._reset_api_client()

        language_values = await self._language_values(self._platform)
        if selected_language not in language_values:
            return self.async_show_form(
                step_id="user",
                errors={"base": "invalid_response"},
                data_schema=await self._user_form_schema(
                    default_email=email,
                    default_platform=self._platform,
                ),
            )

        api = await self._api_client()
        try:
            await api.ensure_auth(email, password)
            objects = await api.get_objects()
        except ApiError:
            return self.async_show_form(
                step_id="user",
                errors={"base": "auth"},
                data_schema=await self._user_form_schema(
                    default_email=email,
                    default_platform=self._platform,
                    default_language=selected_language,
                ),
            )

        self._email = email
        self._password = password
        self._language = selected_language
        self._object_choices = [(obj.id, f"{obj.name} (id={obj.id})") for obj in objects]

        if not self._object_choices:
            return self.async_abort(reason="invalid_response")

        return await self.async_step_select_site()

    async def async_step_select_site(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect object scope for this entry from available list."""
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
                    }
                ),
            )

        selected_object_id = int(user_input[CONF_OBJECT_ID])

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
                    }
                ),
            )

        self._selected_object_id = selected_object_id
        self._module_choices = _module_choices([m.model_dump(mode="json") for m in modules])
        if not self._module_choices:
            return self.async_show_form(
                step_id="select_site",
                errors={"base": "invalid_response"},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OBJECT_ID, default=selected_object_id): vol.In(object_values),
                    }
                ),
            )

        return await self.async_step_select_modules()

    async def async_step_select_modules(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect module scope for this entry from available list."""
        if self._email is None or self._password is None or self._selected_object_id is None:
            return await self.async_step_user()
        if not self._module_choices:
            return await self.async_step_select_site()

        module_values = {module_id: label for module_id, label in self._module_choices}
        default_modules = [module_id for module_id, _ in self._module_choices]
        filter_values = _entity_filter_mode_values()
        default_mode = str(self._entity_filter_mode or DEFAULT_ENTITY_FILTER_MODE).strip().lower()
        if default_mode not in filter_values:
            default_mode = DEFAULT_ENTITY_FILTER_MODE

        module_filter_defaults = {
            module_id: str(self._module_filter_modes.get(module_id, default_mode)).strip().lower()
            for module_id, _ in self._module_choices
        }
        for module_id, mode in list(module_filter_defaults.items()):
            if mode not in filter_values:
                module_filter_defaults[module_id] = default_mode

        if user_input is None:
            return self.async_show_form(
                step_id="select_modules",
                data_schema=_build_modules_step_schema(
                    module_choices=self._module_choices,
                    module_values=module_values,
                    default_modules=default_modules,
                    module_filter_defaults=module_filter_defaults,
                    filter_values=filter_values,
                ),
            )

        selected_modules = [str(module) for module in user_input.get(CONF_MODULES, [])]
        available_codes = set(module_values)
        selected_filter_modes = _extract_selected_module_filter_modes(
            user_input=user_input,
            module_ids=selected_modules,
            default_mode=default_mode,
        )
        if not selected_modules or any(module not in available_codes for module in selected_modules):
            return self.async_show_form(
                step_id="select_modules",
                errors={"base": "invalid_response"},
                data_schema=_build_modules_step_schema(
                    module_choices=self._module_choices,
                    module_values=module_values,
                    default_modules=default_modules,
                    module_filter_defaults=module_filter_defaults,
                    filter_values=filter_values,
                ),
            )
        if selected_filter_modes is None:
            return self.async_show_form(
                step_id="select_modules",
                errors={"base": "invalid_response"},
                data_schema=_build_modules_step_schema(
                    module_choices=self._module_choices,
                    module_values=module_values,
                    default_modules=selected_modules,
                    module_filter_defaults=module_filter_defaults,
                    filter_values=filter_values,
                ),
            )

        self._module_filter_modes = selected_filter_modes
        self._entity_filter_mode = next(iter(selected_filter_modes.values()), default_mode)

        await self.async_set_unique_id(f"{self._platform}:{self._email}:{self._selected_object_id}")
        self._abort_if_unique_id_configured()

        bootstrap = await async_build_bootstrap_payload(
            api=await self._api_client(),
            object_id=self._selected_object_id,
            modules=selected_modules,
            language=self._language,
            entity_filter_mode=self._entity_filter_mode,
            module_filter_modes=self._module_filter_modes,
        )

        data = {
            CONF_EMAIL: self._email,
            CONF_PASSWORD: self._password,
            CONF_BACKEND_PLATFORM: self._platform,
            CONF_LANGUAGE: self._language,
            CONF_ENTITY_FILTER_MODE: self._entity_filter_mode,
            CONF_MODULE_FILTER_MODES: bootstrap.get(CONF_MODULE_FILTER_MODES, self._module_filter_modes),
            CONF_OBJECT_ID: self._selected_object_id,
            CONF_MODULES: selected_modules,
            CONF_ENTITY_DESCRIPTORS: bootstrap[CONF_ENTITY_DESCRIPTORS],
            CONF_MODULES_META: bootstrap[CONF_MODULES_META],
        }

        return self.async_create_entry(title=f"{self._email} ({self._platform}, id={self._selected_object_id})", data=data)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start re-authentication flow."""
        self._email = str(entry_data.get(CONF_EMAIL, ""))
        self._platform = str(entry_data.get(CONF_BACKEND_PLATFORM, Platform.BRAGERONE.value)).strip().lower()
        await self._reset_api_client()
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
        self._config_entry = config_entry
        self._selected_object_id: int | None = None
        self._module_choices: list[tuple[str, str]] = []

    async def _fetch_object_choices(self) -> list[tuple[int, str]]:
        email = str(self._config_entry.data.get(CONF_EMAIL, "")).strip()
        password = str(self._config_entry.data.get(CONF_PASSWORD, ""))
        platform = str(self._config_entry.data.get(CONF_BACKEND_PLATFORM, Platform.BRAGERONE.value)).strip().lower()

        api = BragerOneApiClient(server=server_for(platform))
        try:
            await api.ensure_auth(email, password)
            objects = await api.get_objects()
        finally:
            await api.close()

        return [(obj.id, f"{obj.name} (id={obj.id})") for obj in objects]

    async def _fetch_module_choices(self, object_id: int) -> list[tuple[str, str]]:
        email = str(self._config_entry.data.get(CONF_EMAIL, "")).strip()
        password = str(self._config_entry.data.get(CONF_PASSWORD, ""))
        platform = str(self._config_entry.data.get(CONF_BACKEND_PLATFORM, Platform.BRAGERONE.value)).strip().lower()

        api = BragerOneApiClient(server=server_for(platform))
        try:
            await api.ensure_auth(email, password)
            modules = await api.get_modules(object_id)
        finally:
            await api.close()

        return _module_choices([m.model_dump(mode="json") for m in modules])

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select object scope from available objects list."""
        object_choices = await self._fetch_object_choices()
        if not object_choices:
            return self.async_abort(reason="invalid_response")

        object_values = {obj_id: label for obj_id, label in object_choices}
        default_object = int(
            self._config_entry.options.get(
                CONF_OBJECT_ID,
                self._config_entry.data.get(CONF_OBJECT_ID, object_choices[0][0]),
            )
        )
        if default_object not in object_values:
            default_object = object_choices[0][0]

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OBJECT_ID, default=default_object): vol.In(object_values),
                    }
                ),
            )

        self._selected_object_id = int(user_input[CONF_OBJECT_ID])
        self._module_choices = await self._fetch_module_choices(self._selected_object_id)
        if not self._module_choices:
            return self.async_show_form(
                step_id="init",
                errors={"base": "invalid_response"},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_OBJECT_ID, default=default_object): vol.In(object_values),
                    }
                ),
            )

        return await self.async_step_modules()

    async def async_step_modules(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select module scope from available modules list."""
        if self._selected_object_id is None:
            return await self.async_step_init()
        if not self._module_choices:
            self._module_choices = await self._fetch_module_choices(self._selected_object_id)

        module_values = {module_id: label for module_id, label in self._module_choices}
        existing_modules_raw = self._config_entry.options.get(CONF_MODULES, self._config_entry.data.get(CONF_MODULES, []))
        existing_modules = [str(module) for module in existing_modules_raw] if isinstance(existing_modules_raw, list) else []
        default_modules = [module_id for module_id, _ in self._module_choices if module_id in set(existing_modules)]
        if not default_modules:
            default_modules = [module_id for module_id, _ in self._module_choices]

        filter_values = _entity_filter_mode_values()
        default_filter_mode = (
            str(
                self._config_entry.options.get(
                    CONF_ENTITY_FILTER_MODE,
                    self._config_entry.data.get(CONF_ENTITY_FILTER_MODE, DEFAULT_ENTITY_FILTER_MODE),
                )
            )
            .strip()
            .lower()
        )
        if default_filter_mode not in filter_values:
            default_filter_mode = DEFAULT_ENTITY_FILTER_MODE

        existing_module_modes_raw = self._config_entry.options.get(
            CONF_MODULE_FILTER_MODES,
            self._config_entry.data.get(CONF_MODULE_FILTER_MODES, {}),
        )
        existing_module_modes = existing_module_modes_raw if isinstance(existing_module_modes_raw, dict) else {}
        module_filter_defaults = {
            module_id: str(existing_module_modes.get(module_id, default_filter_mode)).strip().lower()
            for module_id, _ in self._module_choices
        }
        for module_id, mode in list(module_filter_defaults.items()):
            if mode not in filter_values:
                module_filter_defaults[module_id] = default_filter_mode

        if user_input is None:
            return self.async_show_form(
                step_id="modules",
                data_schema=_build_modules_step_schema(
                    module_choices=self._module_choices,
                    module_values=module_values,
                    default_modules=default_modules,
                    module_filter_defaults=module_filter_defaults,
                    filter_values=filter_values,
                ),
            )

        selected_modules = [str(module) for module in user_input.get(CONF_MODULES, [])]
        selected_filter_modes = _extract_selected_module_filter_modes(
            user_input=user_input,
            module_ids=selected_modules,
            default_mode=default_filter_mode,
        )
        if not selected_modules or any(module not in module_values for module in selected_modules):
            return self.async_show_form(
                step_id="modules",
                errors={"base": "invalid_response"},
                data_schema=_build_modules_step_schema(
                    module_choices=self._module_choices,
                    module_values=module_values,
                    default_modules=default_modules,
                    module_filter_defaults=module_filter_defaults,
                    filter_values=filter_values,
                ),
            )
        if selected_filter_modes is None:
            return self.async_show_form(
                step_id="modules",
                errors={"base": "invalid_response"},
                data_schema=_build_modules_step_schema(
                    module_choices=self._module_choices,
                    module_values=module_values,
                    default_modules=selected_modules,
                    module_filter_defaults=module_filter_defaults,
                    filter_values=filter_values,
                ),
            )

        selected_filter_mode = next(iter(selected_filter_modes.values()), default_filter_mode)

        return self.async_create_entry(
            title="",
            data={
                CONF_OBJECT_ID: self._selected_object_id,
                CONF_MODULES: selected_modules,
                CONF_ENTITY_FILTER_MODE: selected_filter_mode,
                CONF_MODULE_FILTER_MODES: selected_filter_modes,
            },
        )
