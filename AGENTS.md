# AGENTS.md — ha-bragerone

HACS custom integration (`custom_components/habragerone`) connecting BragerOne heating controllers to Home Assistant via the `py-bragerone` library (`pybragerone` package).

## Project shape

- **Platforms**: `sensor` (HA `device_class` / `state_class` / unit constants from bootstrap units), `binary_sensor`, `switch`, `number` (`NumberMode.BOX`), `select`, `button` (no `climate`).
- **Python**: `>=3.14.2,<3.15`; **HA**: `homeassistant>=2026.3.0`; iot_class `cloud_push`.
- **Dependencies**: **uv** (`uv.lock` committed). Runtime deps pinned exactly in `manifest.json`.
- **Build/versioning**: hatchling + hatch-vcs, CalVer from git tags.
- **Releases**: `scripts/release.sh` tags the current branch; HACS zip via `.github/workflows/release.yml`. `main` may cut stable or `aN`/`bN`/`rcN`; `release/*` trains are pre-only (script + workflow refuse stable off main). See `DEVELOPMENT.md` and `.github/branch-protection-checklist.md`.

## Common commands

```bash
uv sync --locked --group dev --group test   # environment (test group holds pytest; required by poe test/cov/validate)
uv run poe fmt                   # ruff format
uv run poe lint                  # ruff check --fix
uv run poe typecheck             # mypy --strict (python_version 3.14, pydantic plugin)
uv run poe test                  # pytest (pytest-homeassistant-custom-component)
uv run poe cov                   # coverage report (the 80% threshold is enforced only by the pre-push hook)
uv run poe patch-cov             # pre-push parity: 80% project + 100% patch vs merge-base origin/main
uv run poe validate              # fmt + lint + typecheck + security + test
```

CI additionally runs hassfest, HACS action, manifest/strings JSON validation, wheel-compat checks, and a Docker matrix against HA `2026.3.0` (declared minimum — bump together with `hacs.json`/`pyproject.toml`) / `latest` / `dev`. Each workflow ends in an aggregate **gate job** (`CI`, `HA Integration Tests`, `HACS Validation`) that fails if any required job fails; the `protect-main` ruleset requires only these gates, so renaming jobs or matrix legs never requires ruleset changes — keep the gate job names stable. CI uploads `coverage.xml` to Codecov (`codecov-commenter` on PRs; skip Dependabot/Renovate and forks). Patch coverage target is 100% on pull requests only (`only_pulls` in `codecov.yml` — avoids false failures on main merge commits with a bad compare base); project coverage is informational — the 80% floor stays on pre-push via `scripts/check_patch_coverage.sh` (`diff-cover` vs `merge-base origin/main`, same diff basis as Codecov PR patch). `manifest.json` is ignored so release version bumps do not affect patch.

## Architecture in one paragraph

All protocol work happens in `pybragerone` (REST prime + Socket.IO deltas). The integration adds a thin HA layer: `config_flow.py` (UI setup, options, reauth; `VERSION = 2`) → `bootstrap.py` (one-time extraction of entity descriptors from the asset catalog, cached in `entry.data[CONF_ENTITY_DESCRIPTORS]`, invalidated by `BOOTSTRAP_VERSION = 14`; also records `upstream_assets_fingerprint` = `{api_version}|{index-*.js}` for diagnostics staleness visibility — mismatch does **not** auto-rebootstrap; number descriptors may include `unit_code` / `transform_scale` / `transform_offset` / `transform_precision` so HA shows SPA display units) → `runtime.py` (`BragerRuntime`: owns the gateway, syncs `ParamStore`, fans out `ParamUpdate`s to listeners — **there is no `DataUpdateCoordinator`**) → platform files create entities from cached descriptors. Writes go the other way: platform entities call `runtime.async_write`, which uses `command_write.prepare_write` (enum label→raw, inverse numeric transform, min/max check, route selection) before dispatching to the gateway.

**Entity creation vs. entity_registry default state (#212):** every permission-gated symbol with a display value becomes an entity — there is no UI-vs-permissions filter mode. `bootstrap.py` separately probes the everyday-UI route set (`build_panel_groups(..., web_ui_only=True)`) and, for symbols on that route set, checks `ParamResolver.parameter_visibility_diagnostics`; the result is persisted per descriptor as `enabled_by_default` (`EntityDescriptor["enabled_by_default"]`, via `entity_common.descriptor_enabled_by_default`) and consumed by every platform as `_attr_entity_registry_enabled_default`. Symbols outside the everyday UI (installer-only panels, write/special extras resolved only via permissions) start disabled in the entity registry; users re-enable them per-entity if needed. Config/options UI only exposes module selection and `CONF_DEVICE_GROUPING` (flat vs group-by-menu) — no filter-mode field.

## Non-negotiable conventions

1. **Push, not poll**: state-bearing entities set `_attr_should_poll = False` and update via `runtime.add_listener()` (and `add_connectivity_listener()` for module online/offline, `add_cloud_session_listener()` for library↔cloud Socket.IO). Never add polling or a coordinator. Command-only entities (`button.py`) have no ParamStore state but still listen for connectivity to drive availability.
2. **Write safety**: every write converts enum label→raw, applies inverse numeric transform, validates against `n`/`x` min/max, and picks the right route (`parameter_write` vs `raw_command`). Invalid input → explicit validation error, never a silent send. Writes are refused when the module is known offline. Select option lists are filtered at bootstrap/`normalize_cached_descriptors` so only labels whose raw values fall within descriptor min/max appear in the UI.
3. **unique_id stability**: `{entry_id}_{devid}_{symbol}` with platform suffix (`_binary`, `_switch`, `_number`, `_select`, `_button`). Module cloud connectivity uses `{entry_id}_{devid}_connectivity_binary` on the internet-module parent device `identifiers={(domain, devid)}` (alarms/activity diagnostics share that device). Library↔cloud session uses `{entry_id}_cloud_session_binary` on a service device `identifiers={(domain, f"entry:{entry_id}")}`. Changing these breaks user setups — treat as breaking change.
4. **Naming**: display name `"{menu_title|panel leaf} - {label}"` via `descriptor_display_name` (never a leading `" - "` for empty/`/` paths; does not embed the full parent→child chain); suggested object id `slugify(f"{devid}_{symbol}")` (stable catalog key — not `module_name` / i18n labels); `_attr_has_entity_name = True`; DeviceInfo identifiers `(domain, devid)` in **flat** grouping (default), manufacturer `"BragerOne"`. Optional **group by menu** (`CONF_DEVICE_GROUPING`) places entities with a stable bootstrap `menu_key` from the **parent** menu route (not each leaf) on child devices `identifiers={(domain, f"{devid}:{menu_key}")}` with `via_device=(domain, devid)` and device name from `menu_group_title` (root panel segment); when route meta is missing for a panel symbol, inherit `menu_key` from a sibling that shares the same `panel_path` / root segment (panel-only feeder setpoints); only then stay on the parent module. Connection entities use SPA `module` i18n labels (never hardcoded). Changing `suggested_object_id` only affects **new** entity allocations; existing entity_ids are not rewritten by HA. Opting into menu grouping remaps device membership (document for users).
5. **English only** in code/comments/docstrings; mypy `--strict`; ruff (line-length 130, Google docstrings).
6. **Credentials**: diagnostics and logs must redact password/tokens.
7. **Library boundary**: don't re-implement protocol logic in the integration — that belongs to `py-bragerone`. Keep `manifest.json` pins and `pyproject.toml` bounds in sync.
8. **Docs parity**: `README.md`, `docs/`, and translations must describe the integration as it is; code changes that alter documented behavior update docs in the same PR, and docs-only changes must match the code — drift in either direction is a defect.

## Testing

- pytest + pytest-asyncio + `pytest-homeassistant-custom-component`; most tests are pure unit tests using `install_pybragerone_stubs()`.
- Cover at minimum: enum conversions (both directions + invalid input), inverse numeric transform, min/max rejection, route selection, bootstrap classification/filtering, entity naming.
- Tests must pass offline.

## Translations & UI strings

New config/options/errors strings go into `strings.json` and English `translations/en.json`; the other 18 locales follow. hassfest validates these in CI.

## Version consistency checklist (watch in reviews)

- `hacs.json` homeassistant minimum vs the `homeassistant` dependency in `pyproject.toml` (must match; `manifest.json` has no HA version field).
- `manifest.json` `py-bragerone==X` pin vs `pyproject.toml` `py-bragerone>=X`.
- ruff `target-version` vs actual runtime Python.

## Cursor Cloud specific instructions

Default Cloud Agent install syncs deps via the sibling `py-bragerone` `.cursor/environment.json` (`uv sync` for both repos). Use `uv run poe …` from this checkout. **Docker is not available** in the current Cloud Agent image — do not use `docker-compose` profiles here.

### Local Home Assistant smoke (UI / pre-release)

Native HA (no Docker), suitable for computer-use / Chrome against `http://127.0.0.1:8123`:

```bash
uv run poe hass-prepare          # config/ + symlink custom_components
uv run poe hass-cloud            # tmux session `ha-bragerone`, --skip-pip, wait for :8123
# optional unreleased library:
USE_LOCAL_PYBRAGERONE=1 uv run poe hass-prepare && uv run poe hass-cloud
```

- `hass-cloud` uses `--skip-pip` so `manifest.json` requirements do not overwrite the uv-managed venv (needed when testing editable sibling `py-bragerone`).
- First browser visit is HA **onboarding** unless `config/.storage` already exists. Cloud smoke owner account (local only, not a secret): username `cursor` / password `cursor`.
- Prefer **English** UI language on this Cloud HA instance (keeps screenshots/logs consistent for agents).
- BragerOne / TiSConnect cloud credentials for re-adding the integration may be saved in the **Chrome password store** on this VM — use those if a config entry must be removed and recreated. Do not commit credentials.
- Attach logs: `tmux -f /exec-daemon/tmux.portal.conf attach -t ha-bragerone` (or `tmux attach -t ha-bragerone`).
- Offline unit tests remain the default gate: `uv run poe test` / `uv run poe validate`.

### UI / integration testing — read-only hardware rule

When exercising the live BragerOne / TiSConnect integration in Home Assistant (computer-use, Chrome, or manual):

- **Do not change controller state.** Never toggle switches, press buttons, change `number`/`select` setpoints, or otherwise write to the device through the integration under test.
- Allowed: open dashboards, inspect entity states/attributes, diagnostics (redacted), config-flow screens that only read/login, logs.
- Forbidden without an explicit user request for that write: any entity service call or UI control that would send a command to the boiler / module.

This protects a real heating system attached to live credentials. Offline unit tests with stubs remain unconstrained.
