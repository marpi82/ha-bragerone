from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pybragerone.api import ApiClient
from pybragerone.gateway import Gateway
from pybragerone.token_store import SharedTokenStore

from .const import DOMAIN
from .token_store import HATokenStore

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    email = entry.data["email"]
    password = entry.data["password"]
    object_id = entry.data["object_id"]
    modules = entry.data["modules"]

    store = HATokenStore(
        loader=lambda: hass.data[DOMAIN].get("token_dict"),
        saver=lambda d: hass.data[DOMAIN].__setitem__("token_dict", d),
        clearer=lambda: hass.data[DOMAIN].pop("token_dict", None),
    )

    api = ApiClient()
    api.wire_token_store(store)
    await api.ensure_auth(email, password)

    gw = Gateway(api, object_id=object_id, modules=modules)
    await gw.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"api": api, "token_store": store, "gw": gw, "email": email}

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN].pop(entry.entry_id)
    email = data["email"]
    SharedTokenStore.release(email)

    gw: Gateway = data["gw"]
    await gw.stop()
    return True
