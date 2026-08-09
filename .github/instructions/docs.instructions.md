---
applyTo: "README.md,docs/**,custom_components/habragerone/strings.json,custom_components/habragerone/translations/**"
---

# Documentation rules

1. **Docs describe the integration as it is, not as it should be**: before editing documented behavior (setup steps, options, entity naming, supported platforms), verify it against `custom_components/habragerone/`. Code changes that alter documented behavior must update the docs in the same PR — drift in either direction is a defect.
2. **UI strings are docs too**: new config/options/error strings go into `strings.json` and English `translations/en.json`; the other locales follow. Entity naming in docs must match `descriptor_display_name` / unique_id patterns in code.
3. **Version references** (minimum HA version, `py-bragerone` pin, Python version) must match `hacs.json`, `manifest.json`, and `pyproject.toml`.
4. **Examples must be runnable**: setup instructions and YAML/service examples must work copy-paste against the current integration.
