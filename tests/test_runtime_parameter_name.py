"""Tests for parameter_write route metadata."""

from __future__ import annotations

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from tests.helpers.descriptors import writable_parameter_descriptor  # noqa: E402
from tests.helpers.fakes import make_runtime  # noqa: E402


@pytest.mark.asyncio
async def test_async_write_parameter_route_includes_parameter_name_from_mapping_raw() -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor()

    await runtime.async_write(descriptor=descriptor, input_display_value=77.0)

    assert len(api.calls) == 1
    assert api.calls[0]["pool"] == "P6"
    assert api.calls[0]["parameter"] == "v0"
    assert api.calls[0]["parameter_name"] == "parameters.PARAM_0"
