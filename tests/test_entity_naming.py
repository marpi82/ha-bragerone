from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.entity_common import descriptor_display_name, descriptor_suggested_object_id  # noqa: E402


def test_descriptor_display_name_uses_leaf_not_full_path() -> None:
    descriptor = {
        "panel_path": "Menu termostatów/Zawór 1",
        "menu_title": "Zawór 1",
        "label": "Obniżenie nastawy zaworu 1 od termostatu",
        "symbol": "PARAM_0",
    }

    assert descriptor_display_name(descriptor) == "Zawór 1 - Obniżenie nastawy zaworu 1 od termostatu"


def test_descriptor_display_name_derives_leaf_from_panel_path() -> None:
    descriptor = {
        "panel_path": "Termostaty/Zawór 1",
        "label": "Termostat pokojowy zaworu 1",
        "symbol": "PARAM_0",
    }

    assert descriptor_display_name(descriptor) == "Zawór 1 - Termostat pokojowy zaworu 1"


def test_descriptor_display_name_without_panel_path() -> None:
    descriptor = {
        "label": "Temperatura kotła",
        "symbol": "PARAM_0",
    }

    assert descriptor_display_name(descriptor) == "Temperatura kotła"


def test_descriptor_display_name_rejects_slash_only_panel_path() -> None:
    descriptor = {
        "panel_path": "/",
        "label": "Status dmuchawy",
        "symbol": "STATUS_FAN",
    }

    assert descriptor_display_name(descriptor) == "Status dmuchawy"


def test_descriptor_display_name_rejects_empty_and_dot_paths() -> None:
    assert descriptor_display_name({"panel_path": "   ", "label": "Praca pompy"}) == "Praca pompy"
    assert descriptor_display_name({"panel_path": "//", "label": "Praca pompy"}) == "Praca pompy"
    assert descriptor_display_name({"menu_title": "/", "label": "Praca pompy"}) == "Praca pompy"


def test_descriptor_display_name_prefers_menu_title_over_path() -> None:
    descriptor = {
        "panel_path": "Menu termostatów/Zawór 1",
        "menu_title": "Zawór 1",
        "label": "Status",
    }
    assert descriptor_display_name(descriptor) == "Zawór 1 - Status"


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
