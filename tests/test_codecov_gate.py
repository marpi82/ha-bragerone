"""Regression coverage for the Codecov gate configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_CODECOV_CONFIG = _REPO_ROOT / "codecov.yml"
_PATCH_COVERAGE_SCRIPT = _REPO_ROOT / "scripts" / "check_patch_coverage.sh"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a repository YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_codecov_patch_status_stays_pr_only() -> None:
    """Patch coverage stays strict on pull requests while project coverage is informational."""
    config = _load_yaml(_CODECOV_CONFIG)

    patch_status = config["coverage"]["status"]["patch"]["default"]
    project_status = config["coverage"]["status"]["project"]["default"]

    assert patch_status == {
        "target": "100%",
        "threshold": "0%",
        "only_pulls": True,
    }
    assert project_status == {"informational": True}
    assert "scripts/**/*" in config["ignore"]
    assert "tests/**/*" in config["ignore"]


def test_ci_tests_job_uploads_coverage_for_prs_and_pushes() -> None:
    """The test workflow keeps separate Codecov upload behavior for PRs and pushes."""
    workflow = _load_yaml(_CI_WORKFLOW)

    steps = workflow["jobs"]["tests"]["steps"]
    pr_step = next((step for step in steps if step.get("name") == "Upload coverage reports to Codecov (pull request)"), None)
    assert pr_step is not None, "Missing Codecov PR upload step in CI workflow"
    push_step = next((step for step in steps if step.get("name") == "Upload coverage reports to Codecov (push)"), None)
    assert push_step is not None, "Missing Codecov push upload step in CI workflow"

    expected_action = "codecov/codecov-action@fb8b3582c8e4def4969c97caa2f19720cb33a72f"

    assert pr_step["if"] == "${{ github.event_name == 'pull_request' && github.event.pull_request.head.repo.fork == false }}"
    assert pr_step["uses"] == expected_action
    assert pr_step["with"] == {
        "files": "./coverage.xml",
        "flags": "unittests",
        "name": "ha-bragerone",
        "fail_ci_if_error": False,
    }

    assert push_step["if"] == "${{ github.event_name != 'pull_request' }}"
    assert push_step["uses"] == expected_action
    assert push_step["with"] == {
        "files": "./coverage.xml",
        "flags": "unittests",
        "name": "ha-bragerone",
        "fail_ci_if_error": False,
        "token": "${{ secrets.CODECOV_TOKEN }}",
    }


def test_patch_coverage_script_keeps_codecov_parity() -> None:
    """The local patch coverage script mirrors the documented Codecov thresholds."""
    script = _PATCH_COVERAGE_SCRIPT.read_text(encoding="utf-8")

    assert "--cov-fail-under=80" in script
    assert 'echo "patch coverage: skip (origin/main unavailable)"' in script
    assert 'compare_ref="$(git merge-base HEAD origin/main)"' in script
    assert "uv run --group test diff-cover coverage.xml \\" in script
    assert '--compare-branch="${compare_ref}" \\' in script
    assert "--fail-under=100 \\" in script
    assert "--show-uncovered" in script
