"""Soft-compat Module.devices → get_module_menu devices= (#438)."""

from __future__ import annotations

import inspect
import types
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.habragerone.bootstrap import (
    _call_kwargs_with_optional_devices,
    _device_menu_refs_from_module,
)
from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from tests.helpers.fakes import make_runtime  # noqa: E402


def test_call_kwargs_with_optional_devices_only_when_supported() -> None:
    """Older callables without devices= keep kwargs unchanged."""

    def _legacy(*, device_menu: int) -> None:
        _ = device_menu

    def _modern(*, device_menu: int, devices: object | None = None) -> None:
        _ = device_menu, devices

    refs = [SimpleNamespace(manuf_code=1, dev_code=2, fw="1.0")]
    legacy = _call_kwargs_with_optional_devices(
        inspect.signature(_legacy),
        {"device_menu": 0},
        refs,  # type: ignore[arg-type]
    )
    assert "devices" not in legacy

    modern = _call_kwargs_with_optional_devices(
        inspect.signature(_modern),
        {"device_menu": 0},
        refs,  # type: ignore[arg-type]
    )
    assert modern["devices"] is refs


def test_device_menu_refs_from_module_none_without_devices() -> None:
    """Modules without devices yield None (skip devices=)."""
    assert _device_menu_refs_from_module(SimpleNamespace()) is None
    assert _device_menu_refs_from_module(SimpleNamespace(devices=[])) is None


def test_device_menu_refs_from_module_parses_when_helper_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the library helper is available, refs are built from Module.devices."""
    devices = [{"manuf_code": 67, "dev_code": 7, "sw_ver_num": "2.08"}]
    seen: list[object] = []

    class _Ref:
        def __init__(self, manuf_code: int, dev_code: int, fw: str) -> None:
            self.manuf_code = manuf_code
            self.dev_code = dev_code
            self.fw = fw

    def _helper(raw: object) -> list[_Ref]:
        seen.append(raw)
        assert raw is devices
        return [_Ref(67, 7, "2.08")]

    _install_modules_helper(monkeypatch, _helper)
    refs = _device_menu_refs_from_module(SimpleNamespace(devices=devices))
    assert refs is not None
    assert len(refs) == 1
    assert refs[0].manuf_code == 67
    assert refs[0].dev_code == 7
    assert refs[0].fw == "2.08"
    assert seen == [devices]


def test_device_menu_refs_import_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """ImportError from missing modules package is treated as unsupported."""

    def _boom(_name: str) -> Any:
        raise ImportError("no package")

    monkeypatch.setattr("importlib.import_module", _boom)
    assert _device_menu_refs_from_module(SimpleNamespace(devices=[{"manuf_code": 1, "dev_code": 2}])) is None


def test_device_menu_refs_non_callable_helper_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Older modules module without the helper attribute yields None."""
    fake = types.ModuleType("pybragerone.models.api.modules")
    monkeypatch.setattr("importlib.import_module", lambda _name: fake)
    assert _device_menu_refs_from_module(SimpleNamespace(devices=[{"manuf_code": 1, "dev_code": 2}])) is None


def test_device_menu_refs_empty_helper_result_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper returning [] is normalized to None."""
    fake = types.ModuleType("pybragerone.models.api.modules")
    fake.device_menu_refs_from_module = lambda _devices: []  # type: ignore[attr-defined]
    monkeypatch.setattr("importlib.import_module", lambda _name: fake)
    assert _device_menu_refs_from_module(SimpleNamespace(devices=[{"manuf_code": 1, "dev_code": 2}])) is None


def _install_modules_helper(monkeypatch: pytest.MonkeyPatch, helper: Any) -> None:
    """Inject ``pybragerone.models.api.modules`` for soft-compat unit tests."""
    fake = types.ModuleType("pybragerone.models.api.modules")
    fake.device_menu_refs_from_module = helper  # type: ignore[attr-defined]
    monkeypatch.setattr("importlib.import_module", lambda _name: fake)


@pytest.mark.asyncio
async def test_runtime_menu_for_devid_passes_devices_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime route-visibility menu fetch forwards devices= when signature allows."""
    refs = [SimpleNamespace(manuf_code=67, dev_code=7, fw="2.08")]
    _install_modules_helper(monkeypatch, lambda _devices: refs)

    runtime, _api, _gateway, _store = make_runtime()
    runtime.modules_meta = {
        "DEV1": {
            "device_menu": 0,
            "permissions": ["READ"],
            "devices": [{"manuf_code": 67, "dev_code": 7, "fw": "2.08"}],
        }
    }
    seen: dict[str, Any] = {}

    class _Resolver:
        async def get_module_menu(
            self,
            *,
            device_menu: int,
            permissions: list[str],
            devices: object | None = None,
        ) -> object:
            seen["device_menu"] = device_menu
            seen["permissions"] = permissions
            seen["devices"] = devices
            return SimpleNamespace(routes=[])

    menu = await runtime._menu_for_devid("DEV1", _Resolver())  # type: ignore[arg-type]
    assert menu is not None
    assert seen["device_menu"] == 0
    assert seen["devices"] is refs


@pytest.mark.asyncio
async def test_runtime_menu_for_devid_skips_devices_without_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy get_module_menu without devices= keeps kwargs unchanged."""
    refs = [SimpleNamespace(manuf_code=1, dev_code=2, fw="1.0")]
    _install_modules_helper(monkeypatch, lambda _devices: refs)

    runtime, _api, _gateway, _store = make_runtime()
    runtime.modules_meta = {
        "DEV1": {
            "device_menu": 4,
            "permissions": [],
            "devices": [{"manuf_code": 1, "dev_code": 2, "fw": "1.0"}],
        }
    }
    seen: dict[str, Any] = {}

    class _Resolver:
        async def get_module_menu(self, *, device_menu: int, permissions: list[str]) -> object:
            seen.update({"device_menu": device_menu, "permissions": permissions})
            return SimpleNamespace(routes=[])

    menu = await runtime._menu_for_devid("DEV1", _Resolver())  # type: ignore[arg-type]
    assert menu is not None
    assert "devices" not in seen


@pytest.mark.asyncio
async def test_runtime_menu_for_devid_tolerates_helper_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Helper/import failures still fetch the menu without devices=."""
    runtime, _api, _gateway, _store = make_runtime()
    runtime.modules_meta = {
        "DEV1": {
            "device_menu": 4,
            "permissions": [],
            "devices": [{"manuf_code": 1, "dev_code": 2, "fw": "1.0"}],
        }
    }

    def _boom(_name: str) -> Any:
        raise RuntimeError("import failed")

    monkeypatch.setattr("importlib.import_module", _boom)

    class _Resolver:
        async def get_module_menu(self, **kwargs: Any) -> object:
            assert "devices" not in kwargs
            return SimpleNamespace(routes=[])

    with caplog.at_level("DEBUG"):
        menu = await runtime._menu_for_devid("DEV1", _Resolver())  # type: ignore[arg-type]
    assert menu is not None
    assert "Device menu refs unavailable" in caplog.text
