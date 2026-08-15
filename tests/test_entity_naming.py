from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.entity_common import descriptor_display_name, descriptor_suggested_object_id  # noqa: E402


def test_descriptor_display_name_with_panel_path() -> None:
    descriptor = {
        "panel_path": "Termostaty/Zawór 1",
        "label": "Termostat pokojowy zaworu 1",
        "symbol": "PARAM_0",
    }

    assert descriptor_display_name(descriptor) == "Termostaty/Zawór 1 - Termostat pokojowy zaworu 1"


def test_descriptor_display_name_without_panel_path() -> None:
    descriptor = {
        "label": "Temperatura kotła",
        "symbol": "PARAM_0",
    }

    assert descriptor_display_name(descriptor) == "Temperatura kotła"


def test_descriptor_suggested_object_id_uses_devid_and_symbol() -> None:
    descriptor = {
        "devid": "MODABC123",
        "module_name": "ht_daspell_gl_37kw",
        "symbol": "PARAM_P4_43",
    }

    # module_name must not influence the object id — only devid + symbol.
    assert descriptor_suggested_object_id(descriptor) == "modabc123_param_p4_43"


def test_descriptor_suggested_object_id_falls_back_when_devid_missing() -> None:
    descriptor = {"symbol": "PARAM_0"}
    assert descriptor_suggested_object_id(descriptor) == "device_param_0"
