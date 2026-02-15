# New Session Prompt Template

Use this as the first message in a fresh Copilot session for `ha-bragerone`.

---

I am continuing work on BragerOne Home Assistant integration.

Please load context from:
- `.github/handoff-context.md`
- `.github/copilot-instructions.md`

Current priorities:
1. Implement enum write conversion (display label/option -> raw value) before sending commands.
2. Ensure read/state conversion (raw -> display label) where enum mappings exist.
3. Keep send path safe: inverse numeric transform on write + min/max (`n`/`x`) validation.
4. Add/adjust tests for enum conversion and write validation behavior.

Constraints:
- Python 3.13+, strict typing, ruff + mypy clean.
- Minimal, focused changes only.
- Keep code/comments/docstrings in English.

Please start by:
- scanning existing write entry points,
- proposing a small implementation plan,
- then implementing directly and running lint/typecheck/tests.

---

## Optional Add-ons

If needed, include:
- sample entity/service where enum conversion is currently missing,
- expected mapping example (e.g. `"Eco" -> 2`, `2 -> "Eco"`).
