---
applyTo: "custom_components/habragerone/config_flow.py, custom_components/habragerone/strings.json, custom_components/habragerone/translations/**, custom_components/habragerone/diagnostics.py, custom_components/habragerone/manifest.json"
---

# Config flow, translations & metadata rules

1. **Config flow** (`VERSION = 2`): changes to stored data keys require a migration (see v2 legacy-key migration) or a version bump. Unique ID stays `{platform}:{email}:{object_id}`.
2. **Abort reasons & errors**: use typed abort reasons and per-field errors; never raw exceptions to the UI. Reauth flow must keep working when login handling changes.
3. **Options flow**: changing object/modules/filter mode triggers reload — keep that contract.
4. **Strings**: every new config/options step, error, or abort reason needs `strings.json` + `translations/en.json` entries in the same PR; other locales may follow separately.
5. **manifest.json**: `py-bragerone==X` and `tree-sitter==Y` pins are deliberate (CI checks wheel compatibility for musl/manylinux, x86_64 + aarch64). Bumping pins → check wheel availability. Keep `pyproject.toml` bounds in sync.
6. **Diagnostics**: `async_get_config_entry_diagnostics` must redact credentials; new sensitive fields must be added to the redaction list.
7. **hacs.json**: HA minimum version here and the `homeassistant` dependency in `pyproject.toml` must not drift (`manifest.json` has no HA version field).
