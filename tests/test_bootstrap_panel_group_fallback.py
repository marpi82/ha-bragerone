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
    _build_permission_gated_panel_groups,
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


def test_connection_descriptors_built_from_spa_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    class _LabeledResolver(_RecordingResolver):
        async def resolve_module_connection_labels(self, *, lang: str | None = None) -> dict[str, str]:
            _ = lang
            return {
                "serverConnection": "Server connection status",
                "connection.status": "Connection with module status",
                "connection.index": "Connection with module",
            }

    _RecordingResolver.gated_groups = {"Panel": ["SYM_GATED"]}
    _RecordingResolver.ungated_groups = {}
    _RecordingResolver.calls = []
    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _LabeledResolver)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
        )
    )
    descriptors = payload["connection_descriptors"]
    assert len(descriptors) == 1
    assert descriptors[0]["menu_key"] == "module.connection"
    assert descriptors[0]["label"] == "Connection with module status"
    assert "Connection with module" in descriptors[0]["device_name"]


def test_connection_label_resolve_failure_warns_when_api_supported(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class _BrokenLabels(_RecordingResolver):
        async def resolve_module_connection_labels(self, *, lang: str | None = None) -> dict[str, str]:
            _ = lang
            raise RuntimeError("i18n down")

    _RecordingResolver.gated_groups = {"Panel": ["SYM_GATED"]}
    _RecordingResolver.ungated_groups = {}
    _RecordingResolver.calls = []
    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _BrokenLabels)

    with caplog.at_level(logging.WARNING, logger=BOOTSTRAP_LOGGER):
        payload = asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )
    assert payload["connection_descriptors"] == []
    assert any("Skipping connection_descriptors" in record.getMessage() for record in caplog.records)


def test_connection_label_non_dict_skips_descriptors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NonDictLabels(_RecordingResolver):
        async def resolve_module_connection_labels(self, *, lang: str | None = None) -> object:
            _ = lang
            return ["not", "a", "dict"]

    _RecordingResolver.gated_groups = {"Panel": ["SYM_GATED"]}
    _RecordingResolver.ungated_groups = {}
    _RecordingResolver.calls = []
    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _NonDictLabels)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
        )
    )
    assert payload["connection_descriptors"] == []

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
            _build_permission_gated_panel_groups(
                _AlwaysFailingResolver(),
                device_menu="M1",
                permissions=["DISPLAY_PARAMETER_LEVEL_1"],
                devid="M1",
            )
        )


class _EmptyThenRetryAssets:
    """Return an empty menu first, then a usable menu (or raise) on retry."""

    def __init__(self, *, retry_menu: object | Exception) -> None:
        """Store the second ``get_module_menu`` outcome."""
        self._retry_menu = retry_menu
        self.calls: list[list[str] | None] = []

    async def get_module_menu(
        self,
        *,
        device_menu: str,
        permissions: list[str] | None,
    ) -> object:
        """First call yields no kinds; second call uses the configured retry result."""
        _ = device_menu
        self.calls.append(permissions)
        if len(self.calls) == 1:
            return {"routes": []}
        if isinstance(self._retry_menu, Exception):
            raise self._retry_menu
        return self._retry_menu


class _I18nStub:
    async def get_namespace(self, name: str) -> dict[str, object]:
        _ = name
        return {}


def _resolver_with_assets(assets: _EmptyThenRetryAssets) -> type[_RecordingResolver]:
    """Build a ParamResolver stub that carries menu assets for kind retry coverage."""

    class _Resolver(_RecordingResolver):
        def __init__(self) -> None:
            self._assets = assets
            self._i18n = _I18nStub()

        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _Resolver:
            _ = api, store, lang
            return cls()

        def panel_route_diagnostics_from_menu(
            self,
            menu: object,
            *,
            all_panels: bool,
            web_ui_only: bool,
            routes_i18n: dict[str, object],
        ) -> list[dict[str, object]]:
            _ = menu, all_panels, web_ui_only, routes_i18n
            return []

    return _Resolver


def test_menu_kind_retry_reloads_empty_kinds_with_same_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the first menu parse yields no kinds, retry with the same permission set."""
    assets = _EmptyThenRetryAssets(
        retry_menu={
            "routes": [
                {
                    "name": "Boiler",
                    "parameters": {
                        "read": [{"parameter": {"token": "PARAM_GATED"}}],
                        "write": [],
                        "status": [],
                        "special": [],
                    },
                    "children": [],
                }
            ]
        }
    )
    resolver_cls = _resolver_with_assets(assets)
    _RecordingResolver.gated_groups = {"Panel": ["PARAM_GATED"]}
    _RecordingResolver.ungated_groups = {}
    _RecordingResolver.calls = []
    _RecordingResolver.web_ui_flags = []

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", resolver_cls)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
            entity_filter_mode="ui",
        )
    )

    assert assets.calls == [
        ["DISPLAY_PARAMETER_LEVEL_1"],
        ["DISPLAY_PARAMETER_LEVEL_1"],
    ]
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"PARAM_GATED"}
    debug = payload["bootstrap_debug"]["modules"]["M1"]
    assert debug["menu_symbol_kinds_count"] == 1


def test_menu_kind_retry_failure_is_logged_without_failing_bootstrap(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Retry exceptions stay soft — bootstrap continues without menu kinds."""
    assets = _EmptyThenRetryAssets(retry_menu=RuntimeError("retry menu failed"))
    resolver_cls = _resolver_with_assets(assets)
    _RecordingResolver.gated_groups = {"Panel": ["PARAM_GATED"]}
    _RecordingResolver.ungated_groups = {}
    _RecordingResolver.calls = []
    _RecordingResolver.web_ui_flags = []

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", resolver_cls)

    with caplog.at_level(logging.DEBUG, logger=BOOTSTRAP_LOGGER):
        payload = asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
                entity_filter_mode="ui",
            )
        )

    assert assets.calls == [
        ["DISPLAY_PARAMETER_LEVEL_1"],
        ["DISPLAY_PARAMETER_LEVEL_1"],
    ]
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"PARAM_GATED"}
    assert any("Menu kind retry extraction failed for M1" in record.getMessage() for record in caplog.records)


def test_ui_mode_rejects_symbols_without_display_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPA visibility requires a defined display value — bare writes are dropped."""

    class _NoDisplayResolver(_RecordingResolver):
        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=None, value_label=None)

    _NoDisplayResolver.gated_groups = {"Panel": ["PARAM_BLANK"]}
    _NoDisplayResolver.ungated_groups = {}
    _NoDisplayResolver.calls = []
    _NoDisplayResolver.web_ui_flags = []

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _NoDisplayResolver)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
            entity_filter_mode="ui",
        )
    )

    assert payload["entity_descriptors"] == []
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert rejections == [
        {
            "symbol": "PARAM_BLANK",
            "reason": "no_display_value",
            "value": None,
            "value_label": None,
            "menu_kinds": [],
        }
    ]
