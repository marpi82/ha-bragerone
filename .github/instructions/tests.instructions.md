---
applyTo: "tests/**/*.py"
---

# Test suite rules

1. **Framework**: pytest + pytest-asyncio + `pytest-homeassistant-custom-component`; most tests are pure unit tests with `install_pybragerone_stubs()` — prefer that over booting a full HA instance unless testing real HA wiring.
2. **Offline**: tests must pass without network or real BragerOne credentials.
3. **Mandatory coverage areas** when touching the write path:
   - enum label→raw and raw→label conversion, invalid enum input,
   - inverse numeric transform on write,
   - min/max rejection,
   - command route selection (`parameter_write` vs `raw_command`).
4. **Bootstrap**: classification/filtering changes need descriptor fixtures covering each platform type.
5. **Naming tests**: entity naming/unique_id patterns are contractual — keep regression tests for them.
6. **Style**: same ruff/mypy rules as the integration; coverage gate is `--cov-fail-under=70` (pre-push).
