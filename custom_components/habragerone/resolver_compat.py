"""Signature-compat helpers for forwarding ``devid`` into ``py-bragerone`` ParamResolver.

Multi-module setups need ``devid`` on ``ParamResolver.resolve_value`` and
``compose_mapping_register_value`` (py-bragerone#502). The manifest pin still
targets ``py-bragerone==2026.11.2rc2``, which predates that keyword; the pin
bump awaits py-bragerone#509 on the release train. Until then these helpers
forward ``devid`` only when the installed callable accepts it.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def accepts_devid(func: Callable[..., Any]) -> bool:
    """Return True when *func* accepts a ``devid`` keyword argument."""
    try:
        params = inspect.signature(func).parameters
    except TypeError, ValueError:
        return False
    if "devid" in params:
        return params["devid"].kind is not inspect.Parameter.POSITIONAL_ONLY
    return any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values())


def devid_kwargs(func: Callable[..., Any], devid: str | None) -> dict[str, Any]:
    """Return ``{"devid": devid}`` when *devid* is set and *func* supports it, else ``{}``."""
    if isinstance(devid, str) and devid.strip() and accepts_devid(func):
        return {"devid": devid.strip()}
    return {}


async def resolve_value_for_devid(resolver: Any, symbol: str, *, devid: str | None = None) -> Any:
    """Call ``resolver.resolve_value`` forwarding *devid* when supported."""
    resolve = resolver.resolve_value
    return await resolve(symbol, **devid_kwargs(resolve, devid))
