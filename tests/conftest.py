import sys
import types

import pytest

pytest.register_assert_rewrite("tests.test_sensor")


def install_pybragerone_stubs() -> None:
    """Install stub modules for optional `pybragerone` imports used by unit tests."""
    pybragerone_stub = types.ModuleType("pybragerone")
    pybragerone_stub.BragerOneApiClient = object
    pybragerone_stub.BragerOneGateway = object
    pybragerone_stub.__path__ = []
    sys.modules.setdefault("pybragerone", pybragerone_stub)

    pybragerone_api_stub = types.ModuleType("pybragerone.api")
    pybragerone_api_stub.__path__ = []
    sys.modules.setdefault("pybragerone.api", pybragerone_api_stub)

    pybragerone_api_server_stub = types.ModuleType("pybragerone.api.server")

    class _Platform:
        BRAGERONE = types.SimpleNamespace(value="bragerone")

    def _server_for(_platform: str) -> object:
        return object()

    pybragerone_api_server_stub.Platform = _Platform
    pybragerone_api_server_stub.server_for = _server_for
    sys.modules.setdefault("pybragerone.api.server", pybragerone_api_server_stub)

    pybragerone_models_stub = types.ModuleType("pybragerone.models")
    pybragerone_models_stub.__path__ = []
    sys.modules.setdefault("pybragerone.models", pybragerone_models_stub)

    pybragerone_models_param_stub = types.ModuleType("pybragerone.models.param")
    pybragerone_models_param_stub.ParamStore = object
    sys.modules.setdefault("pybragerone.models.param", pybragerone_models_param_stub)

    pybragerone_models_param_resolver_stub = types.ModuleType("pybragerone.models.param_resolver")
    pybragerone_models_param_resolver_stub.ParamResolver = object
    sys.modules.setdefault("pybragerone.models.param_resolver", pybragerone_models_param_resolver_stub)

    pybragerone_models_events_stub = types.ModuleType("pybragerone.models.events")
    pybragerone_models_events_stub.ParamUpdate = object
    sys.modules.setdefault("pybragerone.models.events", pybragerone_models_events_stub)
