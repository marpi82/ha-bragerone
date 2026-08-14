# Bugbot rules — ha-bragerone

Project-specific review gates for Cursor Bugbot (PR reviews and local `/review-bugbot`).
Keep findings actionable; prefer blocking bugs over style nits already covered by ruff/mypy/CI.

## Architecture

- Flag any new polling (`should_poll = True`), `DataUpdateCoordinator`, or periodic REST refresh for state-bearing entities. State updates must come from `runtime.add_listener()` / push. Buttons may stay listener-free.
- Flag re-implementation of Brager protocol / catalog / Socket.IO logic inside `custom_components/` — that belongs in `py-bragerone`.
- Flag writes that skip enum label→raw conversion, inverse numeric transform, min/max (`n`/`x`) validation, or route selection (`parameter_write` vs `raw_command`). Invalid input must raise, never send silently.

## Stability / breaking changes

- Treat changes to `unique_id` patterns (`{entry_id}_{devid}_{symbol}` + platform suffix) as **blocking** unless the PR explicitly documents a migration / breaking change.
- Flag descriptor-shape or classification changes that omit a `BOOTSTRAP_VERSION` bump when cached `CONF_ENTITY_DESCRIPTORS` would go stale.
- Flag DeviceInfo identifier changes away from `(domain, devid)` without an explicit migration plan.

## Security & secrets

- Flag logs, diagnostics, or committed fixtures that expose passwords, tokens, or live account dumps. Diagnostics must redact credentials.
- Flag hardcoded credentials or `.env` secrets in the tree.

## Quality

- English only in code, comments, and docstrings.
- New/changed write-path or classification behavior without matching tests is a blocking bug when practical to test offline.
- Docs/translations drift: user-facing behavior changes without `README.md` / `docs/` / `strings.json` + `translations/en.json` updates are defects.
- Version pin drift is blocking: `manifest.json` `py-bragerone==X` ↔ `pyproject.toml`; `hacs.json` HA minimum ↔ `homeassistant` dependency.

## Non-blocking

- Pure formatting / import-order nits (CI handles them).
- `TODO` / `FIXME` that reference an existing issue number.
