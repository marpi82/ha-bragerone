from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

# Z Twojej biblioteki:
from pybragerone.api import ApiClient, ApiError
# from pybragerone.token_store import SharedTokenStore  # opcjonalnie, jeśli chcesz wspólny store tutaj


# ---- Pomocnicze funkcje do pobierania danych --------------------------------


async def _fetch_objects(api: ApiClient) -> List[Dict[str, Any]]:
    """
    Zwróć listę obiektów (instalacji) dla zalogowanego użytkownika.
    Oczekiwany kształt elementu: {"id": 439, "name": "Dom", ...}
    """
    status, data, _ = await api._req("GET", "/v1/objects", auth=True)
    if status != 200 or not isinstance(data, (list, dict)):
        raise ApiError(status, {"message": "Invalid objects response"}, {})
    # API bywa różne: czasem lista, czasem {"data":[...]}
    items = data if isinstance(data, list) else data.get("data", [])
    return [x for x in items if isinstance(x, dict) and "id" in x]


async def _fetch_modules_for_object(api: ApiClient, object_id: int) -> List[Dict[str, Any]]:
    """
    Zwróć listę modułów dla obiektu (paginacja ustawiona „szeroko”).
    Oczekiwany kształt elementu: {"devid": "FTTCTBSLCE", "name": "...", "moduleVersion": "...", ...}
    """
    # Dopasuj do swojego wrappera/paramów – to wariant zgodny z wcześniejszymi przykładami.
    path = f"/v1/modules?page=1&limit=999&group_id={object_id}"
    status, data, _ = await api._req("GET", path, auth=True)
    if status != 200 or not isinstance(data, dict) or "data" not in data:
        raise ApiError(status, {"message": "Invalid modules response"}, {})
    rows = data.get("data") or []
    return [x for x in rows if isinstance(x, dict) and ("devid" in x or "code" in x or "id" in x)]


def _modules_choices(mods: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """
    Utwórz listę (value,label) do HA form.
    value = devid (preferowane) / code / id
    label = "Name  code=DEVID  ver=Vx"
    """
    out: List[Tuple[str, str]] = []
    for m in mods:
        code = m.get("devid") or m.get("code") or str(m.get("id"))
        if not code:
            continue
        name = m.get("name") or m.get("moduleTitle") or "Module"
        ver = m.get("moduleVersion") or m.get("gateway", {}).get("version") or "-"
        label = f"{name}  code={code}  ver={ver}"
        out.append((code, label))
    return out


# ---- Config Flow -------------------------------------------------------------


class BragerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Dwustopniowy flow: logowanie -> wybór obiektu i modułów."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: Optional[str] = None
        self._password: Optional[str] = None

        self._objects: List[Dict[str, Any]] = []
        self._modules: List[Dict[str, Any]] = []

        self._selected_object_id: Optional[int] = None
        self._selected_modules: List[str] = []

        # API trzymamy tymczasowo na czas flow; właściwą instancję budujesz w __init__.py integracji
        self._api: Optional[ApiClient] = None

    async def _get_api(self) -> ApiClient:
        """Daj tymczasowy ApiClient (bez token cache’a – lub z, jeśli podłączysz SharedTokenStore)."""
        if self._api is None:
            # Jeśli chcesz globalny token store już na etapie flow:
            # email = self._email or ""
            # self._api = ApiClient(
            #     token_loader=lambda: SharedTokenStore._tokens.get(email),
            #     token_saver=lambda tok: SharedTokenStore._tokens.__setitem__(email, tok),
            # )
            self._api = ApiClient()
        return self._api

    # ---- Krok 1: logowanie ---------------------------------------------------

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
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

        email = user_input[CONF_EMAIL].strip()
        password = user_input[CONF_PASSWORD]

        api = await self._get_api()
        try:
            await api.ensure_auth(email, password)
        except ApiError as e:
            err_key = "auth" if e.args else "unknown"
            return self.async_show_form(
                step_id="user",
                errors={"base": err_key},
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_EMAIL, default=email): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
            )

        # zapamiętaj – będą potrzebne w kolejnym kroku
        self._email, self._password = email, password

        # Przejdź do wyboru instalacji/modułów
        return await self.async_step_select_site()

    # ---- Krok 2: wybór obiektu i modułów ------------------------------------

    async def async_step_select_site(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        api = await self._get_api()

        # jeśli to pierwsze wyświetlenie form – wczytaj listę obiektów
        if not self._objects:
            try:
                self._objects = await _fetch_objects(api)
            except ApiError:
                return self.async_abort(reason="cannot_connect")

        # budowa mapy id->label
        object_choices: List[Tuple[int, str]] = []
        for obj in self._objects:
            oid = obj.get("id")
            name = obj.get("name") or f"Object {oid}"
            if isinstance(oid, int):
                object_choices.append((oid, f"{name}  (id={oid})"))

        # jeśli użytkownik przesłał formularz – waliduj i ewentualnie pobierz moduły
        if user_input is not None:
            selected_oid = int(user_input["object_id"])
            try:
                mods = await _fetch_modules_for_object(api, selected_oid)
            except ApiError:
                return self.async_show_form(
                    step_id="select_site",
                    errors={"base": "invalid_response"},
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                "object_id", default=selected_oid
                            ): vol.In({oid: label for oid, label in object_choices}),
                            vol.Optional("modules"): str,
                        }
                    ),
                )

            self._modules = mods
            mod_choices = _modules_choices(mods)

            # jeśli użytkownik podał moduły (np. ręcznie) – normalizuj i sprawdź, czy istnieją
            modules_csv = (user_input.get("modules") or "").strip()
            if modules_csv:
                selected_modules = [m.strip() for m in modules_csv.split(",") if m.strip()]
                existing_codes = {val for val, _ in mod_choices}
                bad = [m for m in selected_modules if m not in existing_codes]
                if bad:
                    # odśwież formę z listą dostępnych
                    return self.async_show_form(
                        step_id="select_site",
                        errors={"base": "invalid_response"},
                        data_schema=vol.Schema(
                            {
                                vol.Required(
                                    "object_id", default=selected_oid
                                ): vol.In({oid: label for oid, label in object_choices}),
                                vol.Optional(
                                    "modules",
                                    description={"suggested_value": ",".join(existing_codes)},
                                ): str,
                            }
                        ),
                        description_placeholders={
                            "modules": ", ".join(sorted(existing_codes)),
                        },
                    )
                # OK
                self._selected_object_id = selected_oid
                self._selected_modules = selected_modules
                return await self._create_entry()

            # Jeśli jeszcze nie wskazano modułów – pokaż podpowiedź (np. pełną listę w opisie).
            return self.async_show_form(
                step_id="select_site",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            "object_id", default=selected_oid
                        ): vol.In({oid: label for oid, label in object_choices}),
                        vol.Optional(
                            "modules",
                            description={"suggested_value": ",".join([v for v, _ in mod_choices])},
                        ): str,
                    }
                ),
                description_placeholders={
                    "modules": ", ".join([v for v, _ in mod_choices]),
                },
            )

        # Pierwsze renderowanie kroku
        default_oid = object_choices[0][0] if object_choices else 0
        return self.async_show_form(
            step_id="select_site",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "object_id", default=default_oid
                    ): vol.In({oid: label for oid, label in object_choices}),
                    vol.Optional("modules"): str,
                }
            ),
        )

    async def _create_entry(self) -> FlowResult:
        """Zapisz wpis konfiguracyjny."""
        assert self._email and self._password and self._selected_object_id is not None
        title = f"{self._email} (obj {self._selected_object_id})"
        data = {
            CONF_EMAIL: self._email,
            CONF_PASSWORD: self._password,
            "object_id": self._selected_object_id,
            "modules": self._selected_modules,
        }

        # Unikalność: (email, object_id)
        await self.async_set_unique_id(f"{self._email}:{self._selected_object_id}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=title, data=data)

    # ---- Reauth --------------------------------------------------------------

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> FlowResult:
        """Wejście w reauth po 401/403 z integracji."""
        self._email = entry_data.get(CONF_EMAIL)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
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

        email = user_input[CONF_EMAIL].strip()
        password = user_input[CONF_PASSWORD]

        api = await self._get_api()
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

        # Zaktualizuj istniejący wpis
        assert self.source == config_entries.SOURCE_REAUTH
        entry = await self.async_set_unique_id(f"{email}:{self._selected_object_id or ''}", raise_on_progress=False)
        if entry:
            new_data = dict(entry.data)
            new_data[CONF_EMAIL] = email
            new_data[CONF_PASSWORD] = password
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        # fallback – gdyby nie odnalazło wpisu:
        return self.async_create_entry(
            title=email,
            data={CONF_EMAIL: email, CONF_PASSWORD: password, "object_id": 0, "modules": []},
        )

    # ---- Options Flow --------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return BragerOptionsFlowHandler(config_entry)


class BragerOptionsFlowHandler(config_entries.OptionsFlow):
    """Opcje: pozwól zmienić object_id i listę modułów (CSV)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        cur_obj = self.config_entry.data.get("object_id", 0)
        cur_mods = self.config_entry.data.get("modules", [])
        csv = ",".join(cur_mods) if isinstance(cur_mods, list) else str(cur_mods)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("object_id", default=int(cur_obj)): int,
                    vol.Optional("modules", default=csv): str,
                }
            ),
        )
