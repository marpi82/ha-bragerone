# AGENTS.md — ha-bragerone

HACS custom integration (`custom_components/habragerone`) connecting BragerOne heating controllers to Home Assistant via the `py-bragerone` library (`pybragerone` package).

## Project shape

- **Platforms**: `sensor`, `binary_sensor`, `switch`, `number`, `select`, `button` (no `climate`).
- **Python**: `>=3.14.2,<3.15`; **HA**: `homeassistant>=2026.3.0`; iot_class `cloud_push`.
- **Dependencies**: **uv** (`uv.lock` committed). Runtime deps pinned exactly in `manifest.json`.
- **Build/versioning**: hatchling + hatch-vcs, CalVer from git tags.

## Common commands

```bash
uv sync --locked --group dev --group test   # environment (test group holds pytest; required by poe test/cov/validate)
uv run poe fmt                   # ruff format
uv run poe lint                  # ruff check --fix
uv run poe typecheck             # mypy --strict (python_version 3.14, pydantic plugin)
uv run poe test                  # pytest (pytest-homeassistant-custom-component)
uv run poe cov                   # coverage report (the 80% threshold is enforced only by the pre-push hook)
uv run poe validate              # fmt + lint + typecheck + security + test
```

CI additionally runs hassfest, HACS action, manifest/strings JSON validation, wheel-compat checks, and a Docker matrix against HA `2026.3.0` (declared minimum — bump together with `hacs.json`/`pyproject.toml`) / `latest` / `dev`. Each workflow ends in an aggregate **gate job** (`CI`, `HA Integration Tests`, `HACS Validation`) that fails if any required job fails; the `protect-main` ruleset requires only these gates, so renaming jobs or matrix legs never requires ruleset changes — keep the gate job names stable. CI uploads `coverage.xml` to Codecov (`codecov-commenter` on PRs; skip Dependabot/Renovate and forks). Patch coverage target is 100%; project coverage is informational — the 80% floor stays on pre-push. Same-repo PRs re-request GitHub Copilot review via `.github/workflows/copilot-rerequest.yml` (`COPILOT_REVIEW_TOKEN`).

## Architecture in one paragraph

All protocol work happens in `pybragerone` (REST prime + Socket.IO deltas). The integration adds a thin HA layer: `config_flow.py` (UI setup, options, reauth; `VERSION = 2`) → `bootstrap.py` (one-time extraction of entity descriptors from the asset catalog, cached in `entry.data[CONF_ENTITY_DESCRIPTORS]`, invalidated by `BOOTSTRAP_VERSION = 4`) → `runtime.py` (`BragerRuntime`: owns the gateway, syncs `ParamStore`, fans out `ParamUpdate`s to listeners — **there is no `DataUpdateCoordinator`**) → platform files create entities from cached descriptors. Writes go the other way: platform entities call `runtime.async_write`, which uses `command_write.prepare_write` (enum label→raw, inverse numeric transform, min/max check, route selection) before dispatching to the gateway.

## Non-negotiable conventions

1. **Push, not poll**: state-bearing entities set `_attr_should_poll = False` and update via `runtime.add_listener()`. Never add polling or a coordinator. Exception: command-only entities (`button.py`) have no state and intentionally no listener.
2. **Write safety**: every write converts enum label→raw, applies inverse numeric transform, validates against `n`/`x` min/max, and picks the right route (`parameter_write` vs `raw_command`). Invalid input → explicit validation error, never a silent send.
3. **unique_id stability**: `{entry_id}_{devid}_{symbol}` with platform suffix (`_binary`, `_switch`, `_number`, `_select`, `_button`). Changing these breaks user setups — treat as breaking change.
4. **Naming**: display name `"{panel_path} - {label}"` via `descriptor_display_name`; suggested object id `slugify(f"{module_name}_{symbol}")`; `_attr_has_entity_name = True`; DeviceInfo identifiers `(domain, devid)`, manufacturer `"BragerOne"`.
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
