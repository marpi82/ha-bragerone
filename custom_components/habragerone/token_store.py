from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import asyncio
from homeassistant.helpers.storage import Store
from homeassistant.core import HomeAssistant

from pybragerone.api import Token


@dataclass
class HATokenStore:
    """HA-persistent token store (per entry)."""
    hass: HomeAssistant
    entry_id: str
    _lock: asyncio.Lock

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._lock = asyncio.Lock()

    def _store(self) -> Store[dict[str, Any]]:
        # Klucz per-config-entry, plik w .storage
        return Store(self.hass, version=1, key=f"bragerone_token_{self.entry_id}")

    async def load(self) -> Optional[Token]:
        async with self._lock:
            data = await self._store().async_load()
            if not isinstance(data, dict):
                return None
            try:
                return Token(
                    access_token=data.get("access_token") or data.get("accessToken"),
                    token_type=data.get("token_type") or data.get("type") or "bearer",
                    refresh_token=data.get("refresh_token") or data.get("refreshToken"),
                    expires_at=data.get("expires_at") or data.get("expiresAt"),
                    objects=data.get("objects") or [],
                )
            except Exception:
                return None

    async def save(self, token: Token) -> None:
        async with self._lock:
            await self._store().async_save(
                {
                    "access_token": token.access_token,
                    "token_type": token.token_type,
                    "refresh_token": token.refresh_token,
                    "expires_at": token.expires_at,
                    "objects": token.objects,
                }
            )

    async def clear(self) -> None:
        async with self._lock:
            await self._store().async_remove()
