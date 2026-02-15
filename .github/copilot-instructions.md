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
- Python 3.13+, strict typing (`mypy --strict`) and Ruff compliance.
- Keep code and comments in English.
- Favor small, testable utilities for:
  - enum conversion,
  - numeric transform inversion,
  - bounds validation,
  - command payload construction.
- Reuse existing architecture patterns in this repository; do not introduce parallel abstractions unless needed.

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

## Change Discipline
- Keep changes focused and minimal.
- Do not modify unrelated files.
- If behavior is ambiguous, implement the simplest interpretation that is safe and testable.
