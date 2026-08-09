---
name: code-review
description: Review checklist for ha-bragerone pull requests. Use when reviewing PRs to verify write-path safety (enum/numeric conversion, bounds, routes), push architecture invariants, Home Assistant conventions, version consistency, tests, and security.
---

# Code Review — ha-bragerone

Review procedure for pull requests to this Home Assistant integration. Work through every section; comment only on real issues, with file/line references and a concrete suggested fix.

## 1. Write-path safety (highest priority — these commands reach physical heating hardware)

- [ ] Enum writes convert display label → raw backend value; invalid labels produce a clear validation error, not a silent send.
- [ ] Reads convert raw → display label where a mapping exists.
- [ ] Numeric writes apply the inverse transform and are validated against `n`/`x` min/max; out-of-range is rejected explicitly.
- [ ] Route selection (`parameter_write` vs `raw_command`) follows existing rules in `command_write.py`.
- [ ] Debug logging covers symbol/entity, display value, raw value, route, validation failures — without logging secrets.

## 2. Architecture invariants

- [ ] Push model preserved: no polling, no `DataUpdateCoordinator`; state-bearing entities use `runtime.add_listener()` and unsubscribe on removal (command-only buttons have no listener by design).
- [ ] Protocol logic stays in `pybragerone`; the integration doesn't re-implement REST/WS/param handling.
- [ ] Descriptor-driven entity creation via `entry.data[CONF_ENTITY_DESCRIPTORS]`; descriptor shape changes bump `BOOTSTRAP_VERSION`.
- [ ] unique_id patterns unchanged (`{entry_id}_{devid}_{symbol}` + platform suffix) — flag any change as breaking.

## 3. Home Assistant conventions

- [ ] Modern config-entry patterns; config flow uses typed abort reasons / per-field errors; reauth intact.
- [ ] New user-facing strings added to `strings.json` + `translations/en.json`.
- [ ] `_attr_has_entity_name = True`, DeviceInfo identifiers `(domain, devid)`, manufacturer `"BragerOne"`.
- [ ] Diagnostics redact credentials and tokens.
- [ ] No new platforms beyond sensor/binary_sensor/switch/number/select/button without discussion.

## 4. Typing & style gates (CI runs these — flag what it can't catch)

- [ ] mypy `--strict` clean; new `Any`/`type: ignore` justified in a comment.
- [ ] Ruff: line length 130, Google docstrings, English-only code/comments.
- [ ] No blocking calls in the event loop.

## 5. Version consistency

- [ ] `hacs.json` HA minimum ↔ `pyproject.toml` `homeassistant` dependency stay in sync (`manifest.json` has no HA version field).
- [ ] `manifest.json` `py-bragerone==X` pin ↔ `pyproject.toml` `py-bragerone>=X` bound in sync; wheel compat (musl/manylinux) considered for pin bumps.

## 6. Tests

- [ ] Write-path changes include the mandatory conversion/bounds/route tests (see `.github/instructions/tests.instructions.md`).
- [ ] Bootstrap classification changes have per-platform descriptor fixtures.
- [ ] Suite passes offline; coverage gate (70%) not weakened.

## 7. Security

- [ ] No credentials/tokens in code, fixtures, logs, or diagnostics output.
- [ ] User input reaching `async_write` validated before hitting the library.

## 8. Docs & metadata

- [ ] **Code↔docs drift (both directions)**: changes to config flow options, entity naming/unique_id patterns, supported platforms, or setup steps must be reflected in `README.md`, `docs/`, and `strings.json`/`translations/`; docs-only changes must match the actual code — flag drift.
- [ ] Version references in docs/examples match `manifest.json`, `hacs.json`, and `pyproject.toml`.

## Stack awareness

- Before flagging stale references or inconsistencies, check whether the PR belongs to a stack: look for "Stacked on #NNN" links or cross-referenced PRs in the PR body and timeline, and fetch those PRs via the GitHub MCP server. If the PR is part of a stack, review the layer in the context of the whole stack — the fix may already exist in a linked layer.

## How to report

- One comment per issue. Use severity to triage what you report — blocker (wrong value could be written to the heater, breaking change without migration, leaked secret), major (CI gate, architecture invariant, missing tests), minor (style, naming, translations) — and report blockers/majors first. Treat this as prioritization guidance, not a required comment format.
- Prefer the smallest change consistent with existing patterns.
- If the PR references an issue, use the GitHub MCP server to read it and confirm the change resolves it; check linked py-bragerone PRs when the library pin changes.
