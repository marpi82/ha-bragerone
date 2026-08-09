---
applyTo: "custom_components/habragerone/config_flow.py, custom_components/habragerone/const.py, custom_components/habragerone/__init__.py, custom_components/habragerone/strings.json, custom_components/habragerone/translations/**, custom_components/habragerone/diagnostics.py, custom_components/habragerone/manifest.json, hacs.json, pyproject.toml"
---

# Config flow, translations & metadata rules

1. **Config flow** (`VERSION = 2`): breaking changes to stored data keys require both a version bump and migration logic in `async_migrate_entry` (see v2 legacy-key migration) — the bump alone leaves old entries on the old schema, and migration alone never runs for entries already at the current version. Unique ID stays `{platform}:{email}:{object_id}`.
2. **Abort reasons & errors**: use typed abort reasons and per-field errors; never raw exceptions to the UI. Reauth flow must keep working when login handling changes.
3. **Options flow**: changing object/modules/filter mode triggers reload — keep that contract.
4. **Strings**: every new config/options step, error, or abort reason needs `strings.json` + `translations/en.json` entries in the same PR; other locales may follow separately.
5. **manifest.json**: `py-bragerone==X` and `tree-sitter==Y` pins are deliberate (CI checks wheel compatibility for musl/manylinux, x86_64 + aarch64). Bumping pins → check wheel availability. Keep the `py-bragerone` bound in `pyproject.toml` in sync (`tree-sitter` is manifest-only, no `pyproject.toml` bound exists).
6. **Diagnostics**: `async_get_config_entry_diagnostics` must redact credentials; new sensitive fields must be added to the redaction list.
7. **hacs.json**: HA minimum version here and the `homeassistant` dependency in `pyproject.toml` must not drift (`manifest.json` has no HA version field).
