"""Bootstrap persistence of upstream assets fingerprint."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

import custom_components.habragerone.upstream_assets as upstream_mod  # noqa: E402
from custom_components.habragerone.bootstrap import async_build_bootstrap_payload  # noqa: E402
from custom_components.habragerone.const import (  # noqa: E402
    CONF_BOOTSTRAP_DEBUG,
    CONF_UPSTREAM_ASSETS_FINGERPRINT,
)


class _FakeParamStore:
    def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
        return None

    def flatten(self) -> dict[str, object]:
        return {"P4.v1": 42}


class _FakeResolver:
    gated_groups: ClassVar[object] = {"Panel": ["SYM1"]}

    @classmethod
    def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
        _ = api, store, lang
        return cls()

    async def build_panel_groups(
        self,
        *,
        device_menu: str,
        permissions: list[str] | None,
        all_panels: bool,
        web_ui_only: bool = False,
    ) -> dict[str, list[str]]:
        _ = device_menu, permissions, all_panels, web_ui_only
        return cast(dict[str, list[str]], self.gated_groups)

    async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
        return {
            symbol: {
                "label": symbol,
                "pool": "P4",
                "chan": "v",
                "idx": 1,
                "mapping": {},
                "min": None,
                "max": None,
                "unit": None,
            }
            for symbol in symbols
        }

    def set_runtime_context(self, context: dict[str, object] | None) -> None:
        _ = context

    async def resolve_value(self, symbol: str) -> SimpleNamespace:
        _ = symbol
        return SimpleNamespace(value=1, value_label="1")

    def parameter_visibility_diagnostics(
        self,
        *,
        desc: dict[str, object],
        resolved: object,
        flat_values: dict[str, object],
    ) -> tuple[bool, dict[str, object]]:
        _ = desc, resolved, flat_values
        return True, {}


class _FakeApi:
    async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
        _ = object_id
        return [
            SimpleNamespace(
                devid="M1",
                name="Module 1",
                moduleTitle="Module 1",
                moduleVersion="1.0",
                gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
                moduleInterface="if1",
                moduleAddress="addr1",
                permissions=["DISPLAY_PARAMETER_LEVEL_1"],
                deviceMenu="M1",
                connectedAt="now",
            )
        ]

    async def modules_parameters_prime(self, module_ids: list[str], return_data: bool = False) -> tuple[int, dict[str, object]]:
        _ = module_ids, return_data
        return 200, {}


@pytest.mark.asyncio
async def test_bootstrap_stores_upstream_assets_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_probe(_api: object) -> str:
        return "2.08|index-Ab12.js"

    monkeypatch.setattr(upstream_mod, "async_probe_upstream_assets_fingerprint", _fake_probe)
    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    payload = await async_build_bootstrap_payload(
        api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
        object_id=1,
        modules=["M1"],
        language="en",
        entity_filter_mode="ui",
    )

    assert payload[CONF_UPSTREAM_ASSETS_FINGERPRINT] == "2.08|index-Ab12.js"
    assert payload[CONF_BOOTSTRAP_DEBUG]["upstream_assets_fingerprint"] == "2.08|index-Ab12.js"


@pytest.mark.asyncio
async def test_bootstrap_omits_fingerprint_when_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_probe(_api: object) -> None:
        return None

    monkeypatch.setattr(upstream_mod, "async_probe_upstream_assets_fingerprint", _fake_probe)
    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    payload = await async_build_bootstrap_payload(
        api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
        object_id=1,
        modules=["M1"],
        language="en",
        entity_filter_mode="ui",
    )

    assert CONF_UPSTREAM_ASSETS_FINGERPRINT not in payload
    assert "upstream_assets_fingerprint" not in payload[CONF_BOOTSTRAP_DEBUG]
