from __future__ import annotations

import asyncio
import logging
import sys
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _build_panel_groups_with_fallback,
    async_build_bootstrap_payload,
)

BOOTSTRAP_LOGGER = "custom_components.habragerone.bootstrap"


class _FakeParamStore:
    def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
        return None

    def flatten(self) -> dict[str, object]:
        return {"P4.v1": 42}


class _RecordingResolver:
    """Resolver stub that records every `build_panel_groups` call.

    `gated_groups` is returned when permissions are passed, `ungated_groups` when they are not.
    Either can be replaced by an exception instance to simulate a failing extraction.
    """

    gated_groups: ClassVar[object] = {}
    ungated_groups: ClassVar[object] = {}
    calls: ClassVar[list[list[str] | None]] = []
    web_ui_flags: ClassVar[list[bool]] = []

    @classmethod
    def from_api(cls, api: object, store: object, lang: object) -> _RecordingResolver:
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
        _ = device_menu, all_panels
        type(self).calls.append(permissions)
        type(self).web_ui_flags.append(web_ui_only)
        result = self.gated_groups if permissions else self.ungated_groups
        if isinstance(result, Exception):
            raise result
        return cast(dict[str, list[str]], result)

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


class _FakeGateway:
    def model_dump(self, mode: str = "json") -> dict[str, object]:
        _ = mode
        return {}


class _FakeApi:
    async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
        _ = object_id
        return [
            SimpleNamespace(
                devid="M1",
                name="Module 1",
                moduleTitle="Module 1",
                moduleVersion="1.0",
                gateway=_FakeGateway(),
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


def _run_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gated_groups: object,
    ungated_groups: object,
    entity_filter_mode: str = "ui",
) -> tuple[dict[str, Any], list[list[str] | None], list[bool]]:
    _RecordingResolver.gated_groups = gated_groups
    _RecordingResolver.ungated_groups = ungated_groups
    _RecordingResolver.calls = []
    _RecordingResolver.web_ui_flags = []

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _RecordingResolver)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
            entity_filter_mode=entity_filter_mode,
        )
    )
    return cast(dict[str, Any], payload), _RecordingResolver.calls, _RecordingResolver.web_ui_flags


def test_empty_gated_panel_groups_stay_empty_without_ungating(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty permission-gated panels must not retry with permissions=None."""
    payload, calls, web_ui_flags = _run_bootstrap(
        monkeypatch,
        gated_groups={},
        ungated_groups={"Panel": ["SYM_FALLBACK"]},
    )

    assert calls == [["DISPLAY_PARAMETER_LEVEL_1"]]
    assert web_ui_flags == [True]
    assert payload["entity_descriptors"] == []


def test_non_empty_gated_panel_groups_skip_the_fallback_call(monkeypatch: pytest.MonkeyPatch) -> None:
    payload, calls, web_ui_flags = _run_bootstrap(
        monkeypatch,
        gated_groups={"Panel": ["SYM_GATED"]},
        ungated_groups={"Panel": ["SYM_FALLBACK"]},
    )

    assert calls == [["DISPLAY_PARAMETER_LEVEL_1"]]
    assert web_ui_flags == [True]
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"SYM_GATED"}


def test_permissions_mode_does_not_request_web_ui_only(monkeypatch: pytest.MonkeyPatch) -> None:
    payload, calls, web_ui_flags = _run_bootstrap(
        monkeypatch,
        gated_groups={"Panel": ["SYM_GATED"]},
        ungated_groups={"Panel": ["SYM_FALLBACK"]},
        entity_filter_mode="permissions",
    )

    assert calls == [["DISPLAY_PARAMETER_LEVEL_1"]]
    assert web_ui_flags == [False]
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"SYM_GATED"}


def test_raising_gated_panel_groups_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extraction errors must fail setup — no silent permissions=None retry."""
    with pytest.raises(RuntimeError, match="gated extraction failed"):
        _run_bootstrap(
            monkeypatch,
            gated_groups=RuntimeError("gated extraction failed"),
            ungated_groups={"Panel": ["SYM_FALLBACK"]},
        )


def test_empty_panel_groups_warn_without_failing_bootstrap(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=BOOTSTRAP_LOGGER):
        payload, calls, _web_ui_flags = _run_bootstrap(monkeypatch, gated_groups={}, ungated_groups={"Panel": []})

    assert calls == [["DISPLAY_PARAMETER_LEVEL_1"]]
    assert payload["entity_descriptors"] == []

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "M1" in warnings[0].getMessage()


def test_failing_panel_group_build_propagates_instead_of_caching_emptiness() -> None:
    """A broken panel extraction must fail setup rather than report zero entities."""

    class _AlwaysFailingResolver:
        async def build_panel_groups(
            self,
            *,
            device_menu: str,
            permissions: list[str] | None,
            all_panels: bool,
            web_ui_only: bool = False,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, web_ui_only
            raise RuntimeError("extraction failed")

    with pytest.raises(RuntimeError, match="extraction failed"):
        asyncio.run(
            _build_panel_groups_with_fallback(
                _AlwaysFailingResolver(),
                device_menu="M1",
                permissions=["DISPLAY_PARAMETER_LEVEL_1"],
                devid="M1",
            )
        )
