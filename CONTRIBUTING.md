# Contributing to ha-bragerone

Thanks for helping improve the BragerOne Home Assistant integration.

## How to contribute

1. Open an issue describing the bug or enhancement (optional but appreciated) — use the [issue templates](https://github.com/marpi82/ha-bragerone/issues/new/choose).
2. Fork the repository and create a feature branch from `main`.
3. Make your changes with tests where practical.
4. Open a pull request against `main` (the [PR template](.github/PULL_REQUEST_TEMPLATE.md) is applied automatically).

The project uses GitHub Issues and Pull Requests for discussion and review. Do **not** file security issues publicly — see [SECURITY.md](SECURITY.md).

Protocol / cloud-API work belongs in [py-bragerone](https://github.com/marpi82/py-bragerone), not this integration.

## Requirements for acceptable contributions

- **Tests**: major new functionality MUST come with tests; bug fixes should add a regression test where practical. All tests must pass offline.
- **Style**: `ruff format` + `ruff check` clean, `mypy --strict` clean, English only in code and docs, Google-style docstrings. Run `uv run poe validate` before pushing (after `uv sync --locked --group dev --group test`).
- **Write safety**: changes to the write path must convert enum label→raw, apply the inverse numeric transform, validate min/max (`n`/`x`), and pick the correct route (`parameter_write` vs `raw_command`). Invalid input must error, never send silently.
- **unique_id**: `{entry_id}_{devid}_{symbol}` plus platform suffix is contractual — changing it is a breaking change.
- **Docs**: user-facing behavior changes update `README.md` / `docs/` / translations in the same PR.

## Development setup

See [DEVELOPMENT.md](DEVELOPMENT.md). Short version:

```bash
uv sync --locked --group dev --group test
uv run pre-commit install
uv run poe validate
```

## Coding standards

- Target Python 3.14.2+ and Home Assistant `>=2026.3.0`.
- Format and lint with **Ruff**; type-check with **mypy** (strict).
- Prefer small, focused PRs with clear commit messages.
- Keep protocol logic in `pybragerone`; do not re-implement REST/WS/param handling here.
- Keep `manifest.json` `py-bragerone==X` in sync with `pyproject.toml`, and `hacs.json` HA minimum in sync with the `homeassistant` dependency.

## Security reports

Do **not** open a public issue for vulnerabilities. Follow [SECURITY.md](SECURITY.md)
and email `marpi82.dev@google.com`.

## License

By contributing, you agree that your contributions are licensed under the MIT License.

## Branch protection

See [.github/branch-protection-checklist.md](.github/branch-protection-checklist.md) for recommended `main` protection settings.
