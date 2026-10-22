"""Soft-compat Module.devices → get_module_menu devices= (#438)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from custom_components.habragerone.bootstrap import (
    _call_kwargs_with_optional_devices,
    _device_menu_refs_from_module,
)


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


def test_device_menu_refs_from_module_parses_when_library_present() -> None:
    """When pybragerone exposes the helper, refs are built from Module.devices."""
    module = SimpleNamespace(
        devices=[{"manuf_code": 67, "dev_code": 7, "sw_ver_num": "2.08"}],
    )
    refs = _device_menu_refs_from_module(module)
    # Soft-compat: if the installed wheel lacks the helper, skip.
    if refs is None:
        return
    assert len(refs) == 1
    assert refs[0].manuf_code == 67
    assert refs[0].dev_code == 7
    assert refs[0].fw == "2.08"
