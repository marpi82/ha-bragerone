## Summary

<!-- What does this PR change and why? Link related issues with "Fixes #N" / "Closes #N" when applicable. -->

## Type of change

<!-- Check all that apply. -->

- [ ] Bug fix (non-breaking)
- [ ] New feature / enhancement (non-breaking)
- [ ] Breaking change (`unique_id`, platforms, config flow version, `BOOTSTRAP_VERSION` / descriptor cache) — call this out explicitly
- [ ] Docs only
- [ ] Tests / CI / tooling / chore

## Checklist

- [ ] English only in code, comments, and docs; Google-style docstrings
- [ ] `uv run poe validate` passes locally (fmt + lint + mypy --strict + security + tests; sync `--group dev --group test` first)
- [ ] Tests added / updated where practical (regression test for bug fixes; cover enum/numeric write safety when touching the write path). Tests pass offline
- [ ] Docs / translations updated when user-facing behavior changes (`README.md`, `docs/`, `strings.json` + `translations/en.json`)
- [ ] Version pins stay consistent (`manifest.json` `py-bragerone==X` ↔ `pyproject.toml`; `hacs.json` HA minimum ↔ `homeassistant` dependency)
- [ ] No secrets / credentials / real device dumps committed; diagnostics remain redacted

## Test plan

<!-- How did you verify this? Commands run, scenarios covered. -->

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

## Notes for reviewers

<!-- Trade-offs, follow-ups, unique_id impact, py-bragerone pin bumps, bootstrap cache invalidation, etc. -->
