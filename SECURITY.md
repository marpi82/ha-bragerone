# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in ha-bragerone, please report it privately:

- **Preferred**: [GitHub private vulnerability reporting](https://github.com/marpi82/ha-bragerone/security/advisories/new)
- **Alternative**: email marpi82.dev@google.com

Please do not create a public GitHub issue for security vulnerabilities.

Vulnerabilities in the `pybragerone` library itself should be reported to [py-bragerone](https://github.com/marpi82/py-bragerone/security/advisories/new).

## Coordinated Vulnerability Disclosure

- **Acknowledgement**: within 3 business days.
- **Initial assessment and severity triage**: within 14 days.
- **Fix or mitigation**: targeted within 90 days of confirmation, depending on severity and complexity.
- **Disclosure**: coordinated with the reporter; a GitHub Security Advisory is published once a fix is released (or when we mutually agree). Reporters are credited in the advisory unless they prefer otherwise.

## Supported Versions

Only the **latest release** receives security fixes; there are no backports to older versions. When a release line stops receiving security updates, it is simply superseded by the newest release — upgrade to stay supported.

## Security tooling

This project uses several tools for code and dependency security scanning:

- **bandit**: Security linting for Python code (pre-commit + `poe security`)
- **ruff** (`S` / flake8-bandit): Fast security lint rules in the same pass as style checks
- **pip-audit**: Dependency vulnerability scanning
- **gitleaks**: Secret scanning in CI

## Security Best Practices

When using ha-bragerone:

1. **Keep the integration updated** via HACS or by tracking GitHub releases.
2. **Secure credentials**: never commit BragerOne passwords or tokens. Diagnostics and logs must redact them.
3. **Home Assistant**: follow Home Assistant's security guidelines for custom components.

## Contact

For security concerns, use [GitHub private vulnerability reporting](https://github.com/marpi82/ha-bragerone/security/advisories/new) or contact: marpi82.dev@google.com
