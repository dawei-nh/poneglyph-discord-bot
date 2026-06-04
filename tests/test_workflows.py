from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_builds_and_scans_container_without_pushing() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "container-security:" in workflow
    assert "docker/setup-buildx-action@v4" in workflow
    assert "docker/build-push-action@v7" in workflow
    assert "push: false" in workflow
    assert "load: true" in workflow
    assert workflow.count("aquasecurity/trivy-action@v0.36.0") == 2
    assert "scan-type: fs" in workflow
    assert "scan-type: image" in workflow
    assert workflow.count("severity: HIGH,CRITICAL") == 2
    assert workflow.count('exit-code: "1"') == 2
    audit_export_command = (
        "uv export --frozen --no-dev --no-hashes --no-emit-project "
        "--format requirements-txt --output-file requirements-audit.txt"
    )
    assert audit_export_command in workflow
    assert (
        "uvx --from pip-audit pip-audit -r requirements-audit.txt --strict" in workflow
    )


def test_ci_preserves_python_quality_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "uv run ruff check ." in workflow
    assert "uv run ruff format --check ." in workflow
    assert "uv run pyright" in workflow
    assert "uv run pytest tests --ignore=tests/live" in workflow
    assert "uv run pytest tests/live -v" in workflow


def test_ci_does_not_reference_dockerhub_publish_secrets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "DOCKERHUB_TOKEN" not in workflow
    assert "DOCKERHUB_USERNAME" not in workflow
    assert "DOCKERHUB_REPOSITORY" not in workflow
