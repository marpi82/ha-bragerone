# Copilot Instructions for ha-bragerone

## Scope and Priorities
- This project integrates BragerOne with Home Assistant.
- Prefer correctness and predictable behavior over feature breadth.
- Keep UX minimal unless explicitly requested.

## Critical Requirements
1. **Enum write conversion is mandatory**
   - Before sending a command, convert user-facing enum option/label to raw backend value.
   - On reads/state updates, convert raw backend value back to display label when mapping exists.
   - Invalid enum input must return a clear validation error.

2. **Numeric write safety**
   - Apply inverse numeric transform on writes when UI value differs from raw protocol value.
   - Validate raw value against min/max constraints (`n`/`x`) before send.
   - Do not send if out-of-range; emit explicit error details.

3. **Prime + WS model**
   - Treat REST prime as required initial state and reconnect recovery.
   - Treat WebSocket as delta stream only.

## Implementation Guidelines
- Python 3.14+, strict typing (`mypy --strict`) and Ruff compliance (line-length 130, Google docstrings).
- Keep code and comments in English.
- Favor small, testable utilities for:
  - enum conversion,
  - numeric transform inversion,
  - bounds validation,
  - command payload construction.
- Reuse existing architecture patterns in this repository; do not introduce parallel abstractions unless needed.
- Home Assistant patterns: state-bearing entities are push-based (`_attr_should_poll = False`) driven by `BragerRuntime` — do not introduce `DataUpdateCoordinator` or polling (command-only buttons have no state subscription by design); descriptor-driven entity creation via cached `entry.data` descriptors; `_attr_has_entity_name = True`.

## Library Boundary (py-bragerone)
- All BragerOne protocol logic lives in the `pybragerone` package (pinned in `manifest.json`). Integration code must not re-implement REST/WS/param logic — extend the library instead.
- `manifest.json` pins exact versions (`py-bragerone==...`); bump deliberately and keep `pyproject.toml` dependency bounds in sync.

## Code Review Priorities
When reviewing pull requests, prioritize (details in `.github/skills/code-review/SKILL.md`):
1. **Write path safety**: enum label→raw conversion, inverse numeric transform, min/max (`n`/`x`) validation, correct route (`parameter_write` vs `raw_command`).
2. **Entity lifecycle**: entities subscribe/unsubscribe to `runtime.add_listener()` correctly; no polling; unique_id patterns preserved (`{entry_id}_{devid}_{symbol}` + platform suffix).
3. **Bootstrap cache**: `BOOTSTRAP_VERSION` bump when descriptor shape changes; cache invalidation correctness.
4. **HA quality scale**: config flow errors with proper abort reasons, reauth, translations for new strings (`strings.json` + `translations/`), diagnostics redact credentials.
5. **Version consistency**: `hacs.json` HA minimum ↔ `pyproject.toml` `homeassistant` dependency, and `manifest.json` `py-bragerone==X` pin ↔ `pyproject.toml` library bound must not drift (`manifest.json` carries no HA/Python version).
6. **Docs consistency (code↔docs)**: changes to config flow options, entity naming, supported platforms, or setup steps must be reflected in `README.md`, `docs/`, and translations; docs-only changes must match the actual code — flag drift in either direction.

## Logging & Diagnostics
- Add debug logs for command write pipeline:
  - symbol/entity,
  - input display value,
  - converted raw value,
  - selected command route,
  - validation failures.
- Avoid noisy logs in normal mode.

## Testing Expectations
Add/maintain tests for:
- enum label -> raw conversion,
- raw -> enum label conversion,
- invalid enum value handling,
- inverse numeric transform on write,
- min/max rejection behavior,
- command route selection behavior.

## CI/CD & GitHub Workflows

- **ci.yml**: lint, mypy, tests (pytest + Codecov upload), hassfest, security, wheel-compat, aggregate `CI` gate
- **ha-integration-test.yml**: Docker matrix against HA `2026.3.0` / `latest` / `dev`
- **hacs.yml**: HACS validation
- **copilot-rerequest.yml**: re-request GitHub Copilot review on same-repo PRs (`COPILOT_REVIEW_TOKEN`)

Issue forms live in `.github/ISSUE_TEMPLATE/`; the PR body template is `.github/PULL_REQUEST_TEMPLATE.md`.

## Change Discipline
- Keep changes focused and minimal.
- Do not modify unrelated files.
- If behavior is ambiguous, implement the simplest interpretation that is safe and testable.
