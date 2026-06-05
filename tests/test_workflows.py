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


def test_publish_workflow_only_runs_on_main_push() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text()

    assert "\non:\n  push:\n" in workflow
    assert "branches: [main]" in workflow
    assert "pull_request" not in workflow
    assert "concurrency:" in workflow
    assert "group: publish-image-main" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "docker/login-action@v4" in workflow
    assert "DOCKERHUB_USERNAME" in workflow
    assert "DOCKERHUB_TOKEN" in workflow
    assert "DOCKERHUB_REPOSITORY" in workflow


def test_publish_workflow_scans_image_before_login_and_push() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text()

    assert "docker/setup-buildx-action@v4" in workflow
    assert "docker/build-push-action@v7" in workflow
    assert "push: false" in workflow
    assert "load: true" in workflow
    assert "aquasecurity/trivy-action@v0.36.0" in workflow
    assert "scan-type: image" in workflow
    assert (
        "image-ref: ${{ secrets.DOCKERHUB_REPOSITORY }}:"
        "sha-${{ steps.vars.outputs.short_sha }}"
    ) in workflow
    assert workflow.index("Trivy image scan") < workflow.index("Login to Docker Hub")
    assert workflow.index("Login to Docker Hub") < workflow.index("Push image")
    assert "push: true" not in workflow


def test_publish_workflow_pushes_expected_tags_after_scan() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text()

    assert "${{ secrets.DOCKERHUB_REPOSITORY }}:latest" in workflow
    assert "${{ secrets.DOCKERHUB_REPOSITORY }}:main" in workflow
    assert (
        "${{ secrets.DOCKERHUB_REPOSITORY }}:sha-${{ steps.vars.outputs.short_sha }}"
        in workflow
    )
    assert 'docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:latest"' in workflow
    assert 'docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:main"' in workflow
    assert (
        'docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:'
        'sha-${{ steps.vars.outputs.short_sha }}"'
    ) in workflow
    assert workflow.index(
        'docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:'
        'sha-${{ steps.vars.outputs.short_sha }}"'
    ) < workflow.index('docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:main"')
    assert workflow.index(
        'docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:main"'
    ) < workflow.index('docker push "${{ secrets.DOCKERHUB_REPOSITORY }}:latest"')
    assert workflow.index("Trivy image scan") < workflow.index("Push image")
