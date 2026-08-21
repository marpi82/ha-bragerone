import asyncio
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from pydantic import BaseModel, Field

pytest.register_assert_rewrite("tests.test_sensor")


class _TokenStub(BaseModel):
    """Minimal Token stand-in for offline token_store tests."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: datetime | None = None
    objects: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class _ModuleConnectivityStub:
    """Minimal ModuleConnectivity stand-in for offline unit tests."""

    devid: str
    online: bool
    source: str = "derived"
    connected_at: int | None = None
    gateway: dict[str, object] | None = None
    online_changed: bool = True
    metadata_changed: bool = False


@pytest.fixture(autouse=True)
def enable_event_loop_debug() -> None:
    """Enable event loop debug mode with a safe fallback when no loop exists."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.set_debug(True)


def install_pybragerone_stubs() -> None:
    """Install stub modules for optional `pybragerone` imports used by unit tests."""
    if getattr(install_pybragerone_stubs, "_installed", False):
        return

    for module_name in list(sys.modules):
        if module_name == "pybragerone" or module_name.startswith("pybragerone."):
            del sys.modules[module_name]

    pybragerone_stub = types.ModuleType("pybragerone")
    pybragerone_stub.BragerOneApiClient = object
    pybragerone_stub.BragerOneGateway = object
    pybragerone_stub.__path__ = []
    sys.modules["pybragerone"] = pybragerone_stub

    pybragerone_api_stub = types.ModuleType("pybragerone.api")
    pybragerone_api_stub.__path__ = []
    sys.modules["pybragerone.api"] = pybragerone_api_stub

    pybragerone_api_server_stub = types.ModuleType("pybragerone.api.server")

    class _Platform:
        BRAGERONE = types.SimpleNamespace(value="bragerone")
        TISCONNECT = types.SimpleNamespace(value="tisconnect")

    def _server_for(_platform: str) -> object:
        return object()

    pybragerone_api_server_stub.Platform = _Platform
    pybragerone_api_server_stub.server_for = _server_for
    sys.modules["pybragerone.api.server"] = pybragerone_api_server_stub

    pybragerone_api_client_stub = types.ModuleType("pybragerone.api.client")

    class _ApiError(Exception):
        pass

    pybragerone_api_client_stub.ApiError = _ApiError
    sys.modules["pybragerone.api.client"] = pybragerone_api_client_stub

    pybragerone_models_stub = types.ModuleType("pybragerone.models")
    pybragerone_models_stub.__path__ = []
    sys.modules["pybragerone.models"] = pybragerone_models_stub

    pybragerone_models_param_stub = types.ModuleType("pybragerone.models.param")
    pybragerone_models_param_stub.ParamStore = object
    sys.modules["pybragerone.models.param"] = pybragerone_models_param_stub

    pybragerone_models_param_resolver_stub = types.ModuleType("pybragerone.models.param_resolver")

    class _ParamResolverStub:
        @staticmethod
        def compose_mapping_register_value(store: object, mapping: object) -> int | float | None:
            """Minimal stub mirroring pybragerone multi-register compose (#327)."""
            if not isinstance(mapping, dict):
                return None
            paths = mapping.get("paths") if isinstance(mapping.get("paths"), dict) else {}
            raw = mapping.get("raw") if isinstance(mapping.get("raw"), dict) else {}
            entries = paths.get("value") if isinstance(paths, dict) else None
            if not isinstance(entries, list) or not entries:
                entries = raw.get("value") if isinstance(raw, dict) else None
            if not isinstance(entries, list) or not entries:
                return None
            if any(isinstance(e, dict) and any(k in e for k in ("if", "elseif", "then", "else")) for e in entries):
                return None

            def _is_selector(entry: object) -> bool:
                if not isinstance(entry, dict):
                    return False
                group = entry.get("group")
                number = entry.get("number")
                use = entry.get("use")
                return isinstance(group, str) and bool(group) and isinstance(number, int) and isinstance(use, str) and bool(use)

            selectors = [entry for entry in entries if _is_selector(entry)]
            if not selectors:
                return None
            needs_compose = len(selectors) >= 2
            if not needs_compose:
                only = selectors[0]
                times = only.get("times")
                needs_compose = bool(only.get("convert")) or (
                    isinstance(times, (int, float)) and not isinstance(times, bool) and float(times) != 1.0
                )
            if not needs_compose:
                return None

            total = 0.0
            found = False
            get_family = getattr(store, "get_family", None)
            if not callable(get_family):
                return None
            for selector in entries:
                if not isinstance(selector, dict):
                    continue
                group = selector.get("group")
                number = selector.get("number")
                use = selector.get("use")
                if not isinstance(group, str) or not isinstance(number, int) or not isinstance(use, str) or not use:
                    continue
                family = get_family(group, number)
                if family is None:
                    continue
                raw_val = family.get(use[0]) if hasattr(family, "get") else None
                if raw_val is None:
                    continue
                try:
                    word_f = float(raw_val)
                except TypeError:
                    continue
                except ValueError:
                    continue
                if selector.get("convert"):
                    word: int | float = int(word_f) & 0xFFFF
                elif word_f.is_integer():
                    word = int(word_f)
                else:
                    word = word_f
                times = selector.get("times", 1)
                if isinstance(times, bool) or not isinstance(times, (int, float)):
                    times_n: int | float = 1
                else:
                    times_n = times
                total += float(word) * float(times_n)
                found = True
            if not found:
                return None
            if float(total).is_integer():
                return int(total)
            return total

    pybragerone_models_param_resolver_stub.ParamResolver = _ParamResolverStub
    sys.modules["pybragerone.models.param_resolver"] = pybragerone_models_param_resolver_stub

    pybragerone_models_events_stub = types.ModuleType("pybragerone.models.events")
    pybragerone_models_events_stub.ParamUpdate = object
    pybragerone_models_events_stub.ModuleConnectivity = _ModuleConnectivityStub
    sys.modules["pybragerone.models.events"] = pybragerone_models_events_stub

    pybragerone_models_catalog_stub = types.ModuleType("pybragerone.models.catalog")
    pybragerone_models_catalog_stub.LiveAssetsCatalog = object
    pybragerone_models_catalog_stub.INDEX_ASSET_RE = __import__("re").compile(r"/assets/(index-[A-Za-z0-9_-]+\.js)")
    sys.modules["pybragerone.models.catalog"] = pybragerone_models_catalog_stub

    pybragerone_models_token_stub = types.ModuleType("pybragerone.models.token")
    pybragerone_models_token_stub.Token = _TokenStub
    sys.modules["pybragerone.models.token"] = pybragerone_models_token_stub

    install_pybragerone_stubs._installed = True  # type: ignore[attr-defined]
