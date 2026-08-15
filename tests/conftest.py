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
    pybragerone_models_param_resolver_stub.ParamResolver = object
    sys.modules["pybragerone.models.param_resolver"] = pybragerone_models_param_resolver_stub

    pybragerone_models_events_stub = types.ModuleType("pybragerone.models.events")
    pybragerone_models_events_stub.ParamUpdate = object
    pybragerone_models_events_stub.ModuleConnectivity = _ModuleConnectivityStub
    sys.modules["pybragerone.models.events"] = pybragerone_models_events_stub

    pybragerone_models_catalog_stub = types.ModuleType("pybragerone.models.catalog")
    pybragerone_models_catalog_stub.LiveAssetsCatalog = object
    sys.modules["pybragerone.models.catalog"] = pybragerone_models_catalog_stub

    pybragerone_models_token_stub = types.ModuleType("pybragerone.models.token")
    pybragerone_models_token_stub.Token = _TokenStub
    sys.modules["pybragerone.models.token"] = pybragerone_models_token_stub

    install_pybragerone_stubs._installed = True  # type: ignore[attr-defined]
