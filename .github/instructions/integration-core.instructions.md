---
applyTo: "custom_components/habragerone/**/*.py"
---

# Integration core rules (apply to all of custom_components/habragerone)

1. **Push architecture**: entities are push-based (`_attr_should_poll = False`) via `BragerRuntime.add_listener()`. Flag any introduction of polling, `DataUpdateCoordinator`, or `async_update` refresh loops.
2. **Listener lifecycle**: entities must unsubscribe in `async_will_remove_from_hass` (or via the `async_on_remove` pattern used in the codebase). Leaked listeners cause duplicate state writes.
3. **Write path** (`command_write.py` / `runtime.async_write`):
   - enum label→raw before send; raw→label on read when a mapping exists;
   - inverse numeric transform applied when UI and protocol scales differ;
   - min/max (`n`/`x`) validated before send — out-of-range must raise, not clamp silently;
   - route selection (`parameter_write` vs `raw_command`) must stay consistent with existing rules.
4. **unique_id / naming**: keep `{entry_id}_{devid}_{symbol}` + platform suffix patterns and `descriptor_display_name` ("{panel_path} - {label}") stable; `_attr_has_entity_name = True`; DeviceInfo identifiers `(domain, devid)`.
5. **Descriptors**: entity creation is descriptor-driven from `entry.data[CONF_ENTITY_DESCRIPTORS]`. Platform classification/filtering changes belong in `bootstrap.py` and require a `BOOTSTRAP_VERSION` bump.
6. **HA APIs**: use modern HA patterns (config entries, no `hass.data` globals beyond the runtime slot, `ConfigEntry` runtime_data pattern where applicable). Target HA `>=2026.8.1`.
7. **Async**: never block the event loop; library calls are awaited; no threads.
8. **Typing/style**: mypy strict, ruff (130 cols, Google docstrings), English only.
9. **Secrets**: never log or expose password/tokens; diagnostics redact them.
