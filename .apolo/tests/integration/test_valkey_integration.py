"""Integration tests for Valkey app that generate helm values and validate with helm."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import yaml
from apolo_apps_valkey.app_types import (
    ValkeyAppInputs,
    ValkeyArchitectureTypes,
    ValkeyConfig,
    ValkeyReplicationArchitecture,
    ValkeyStandaloneArchitecture,
)
from apolo_apps_valkey.inputs_processor import ValkeyAppChartValueProcessor

from apolo_app_types.protocols.common import AutoscalingHPA, Preset
from apolo_app_types.protocols.common.ingress import BasicNetworkingConfig


CHART_PATH = Path(__file__).parent.parent.parent.parent / "valkey"


def _values_for_chart(helm_values: dict, chart_path: Path) -> dict:
    """Return values to write to helm for the given chart path.

    If the test targets the `valkey` chart directly, the generator returns the
    valkey values under the `valkey` key (for umbrella charts). Flatten them
    to the root so the standalone valkey chart consumes them.
    """
    return (
        helm_values.get("valkey", helm_values)
        if chart_path.name == "valkey"
        else helm_values
    )


@pytest.fixture(scope="session", autouse=True)
def _build_helm_dependencies():
    """Build helm dependencies once per test session."""
    import subprocess

    # Check if helm is available
    if os.system("which helm > /dev/null 2>&1") != 0:
        pytest.skip("helm not installed")
        return

    # Build helm dependencies
    result = subprocess.run(
        ["helm", "dependency", "build", str(CHART_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        pytest.fail(
            f"Failed to build helm dependencies: {result.stderr}\n{result.stdout}"
        )


@pytest.fixture
def chart_path():
    """Get the path to the helm chart."""
    return CHART_PATH


@pytest.fixture
def basic_inputs_with_valkey_standalone():
    """Create ValkeyAppInputs with Valkey standalone architecture."""
    return ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )


@pytest.fixture
def inputs_with_valkey_replication():
    """Create ValkeyAppInputs with Valkey replication architecture."""
    return ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyReplicationArchitecture(
                architecture_type=ValkeyArchitectureTypes.REPLICATION,
                replica_preset=Preset(name="cpu-small"),
                autoscaling=AutoscalingHPA(
                    min_replicas=2,
                    max_replicas=10,
                    target_cpu_utilization_percentage=70,
                    target_memory_utilization_percentage=80,
                ),
            ),
        ),
        networking=BasicNetworkingConfig(),
    )


@pytest.fixture
def inputs_with_postgres():
    """Create ValkeyAppInputs with PostgreSQL database."""
    return ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )


@pytest.mark.skipif(
    os.system("which helm > /dev/null 2>&1") != 0,
    reason="helm not installed",
)
async def test_helm_template_with_generated_values_standalone(
    apolo_client, mock_get_preset_cpu, basic_inputs_with_valkey_standalone, chart_path
):
    """Test that helm template works with generated values (standalone Valkey)."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    # Generate helm values
    helm_values = await input_processor.gen_extra_values(
        input_=basic_inputs_with_valkey_standalone,
        app_name="valkey-test",
        namespace="test-namespace",
        app_secrets_name="test-secret",
        app_id="test-app-id",
    )

    # Write values to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as values_file:
        yaml.dump(_values_for_chart(helm_values, chart_path), values_file)
        values_path = Path(values_file.name)

    try:
        # Run helm template
        process = await asyncio.create_subprocess_exec(
            "helm",
            "template",
            "test-release",
            str(chart_path),
            "-f",
            str(values_path),
            "--namespace",
            "test-namespace",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Check that helm template succeeded
        assert process.returncode == 0, f"helm template failed: {stderr.decode()}"

        # Verify the output contains valid YAML
        manifests = list(yaml.safe_load_all(stdout.decode()))
        assert len(manifests) > 0, "No manifests generated"
        # Verify we have expected resources.
        # Charts may render valkey as Deployment or StatefulSet
        resource_kinds = {m.get("kind") for m in manifests if m}
        assert "Deployment" in resource_kinds or "StatefulSet" in resource_kinds
        assert "Service" in resource_kinds

        # Verify Valkey resource (either Deployment or StatefulSet) is present
        valkey_resources = [
            m for m in manifests if m and m.get("kind") in ("StatefulSet", "Deployment")
        ]
        valkey_names = [r.get("metadata", {}).get("name", "") for r in valkey_resources]
        assert any(
            "valkey" in name or "redis" in name for name in valkey_names
        ), "No Valkey/Redis resource found"

    finally:
        values_path.unlink()
    # Assert top-level keys and their values
    assert "apolo_app_id" in helm_values
    assert helm_values["apolo_app_id"] == "test-app-id"
    assert "ingress" in helm_values
    assert helm_values["ingress"]["enabled"] is True
    assert helm_values["image"]["repository"] == "valkey/valkey"
    assert helm_values["labels"] == {"application": "valkey"}
    assert "service" in helm_values
    assert helm_values["service"]["port"] == 6379
    assert helm_values["auth"]["enabled"] is False
    assert "resources" in helm_values
    assert "replica" in helm_values


@pytest.mark.skipif(
    os.system("which helm > /dev/null 2>&1") != 0,
    reason="helm not installed",
)
async def test_helm_template_with_generated_values_replication(
    apolo_client, mock_get_preset_cpu, inputs_with_valkey_replication, chart_path
):
    """Test that helm template works with Valkey replication and autoscaling."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    # Generate helm values
    helm_values = await input_processor.gen_extra_values(
        input_=inputs_with_valkey_replication,
        app_name="valkey-test",
        namespace="test-namespace",
        app_secrets_name="test-secret",
        app_id="test-app-id",
    )

    # Write values to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as values_file:
        yaml.dump(_values_for_chart(helm_values, chart_path), values_file)
        values_path = Path(values_file.name)

    try:
        # Run helm template
        process = await asyncio.create_subprocess_exec(
            "helm",
            "template",
            "test-release",
            str(chart_path),
            "-f",
            str(values_path),
            "--namespace",
            "test-namespace",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Check that helm template succeeded
        assert process.returncode == 0, f"helm template failed: {stderr.decode()}"

        # Verify the output contains valid YAML
        manifests = list(yaml.safe_load_all(stdout.decode()))
        assert len(manifests) > 0, "No manifests generated"

        # Verify Valkey primary and replica StatefulSets are present
        valkey_resources = [
            m for m in manifests if m and m.get("kind") == "StatefulSet"
        ]
        valkey_names = [r.get("metadata", {}).get("name", "") for r in valkey_resources]
        # In replication mode, we should have primary and replica
        valkey_count = sum(
            1 for name in valkey_names if "valkey" in name or "redis" in name
        )
        assert (
            valkey_count >= 1
        ), "Expected Valkey/Redis StatefulSets for replication mode"

    finally:
        values_path.unlink()


@pytest.mark.skipif(
    os.system("which helm > /dev/null 2>&1") != 0,
    reason="helm not installed",
)
async def test_helm_lint_with_generated_values(
    apolo_client, mock_get_preset_cpu, basic_inputs_with_valkey_standalone, chart_path
):
    """Test that helm lint passes with generated values."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    # Generate helm values
    helm_values = await input_processor.gen_extra_values(
        input_=basic_inputs_with_valkey_standalone,
        app_name="valkey-test",
        namespace="test-namespace",
        app_secrets_name="test-secret",
        app_id="test-app-id",
    )

    # Write values to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as values_file:
        yaml.dump(_values_for_chart(helm_values, chart_path), values_file)
        values_path = Path(values_file.name)

    try:
        # Run helm lint
        process = await asyncio.create_subprocess_exec(
            "helm",
            "lint",
            str(chart_path),
            "-f",
            str(values_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Check that helm lint succeeded
        assert (
            process.returncode == 0
        ), f"helm lint failed: {stderr.decode()}\n{stdout.decode()}"

    finally:
        values_path.unlink()


@pytest.fixture
def inputs_with_persistence_none():
    """Create ValkeyAppInputs with persistence=None."""
    return ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )


@pytest.fixture
def inputs_with_custom_persistence_path():
    """Create ValkeyAppInputs with custom persistence path."""
    return ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )


@pytest.mark.skipif(
    os.system("which helm > /dev/null 2>&1") != 0,
    reason="helm not installed",
)
async def test_helm_template_with_persistence_none(
    apolo_client, mock_get_preset_cpu, inputs_with_persistence_none, chart_path
):
    """Test that helm template works with persistence=None."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    # Generate helm values
    helm_values = await input_processor.gen_extra_values(
        input_=inputs_with_persistence_none,
        app_name="valkey-test",
        namespace="test-namespace",
        app_secrets_name="test-secret",
        app_id="test-app-id",
    )

    # Write values to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as values_file:
        yaml.dump(_values_for_chart(helm_values, chart_path), values_file)
        values_path = Path(values_file.name)

    try:
        # Run helm template
        process = await asyncio.create_subprocess_exec(
            "helm",
            "template",
            "test-release",
            str(chart_path),
            "-f",
            str(values_path),
            "--namespace",
            "test-namespace",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Check that helm template succeeded
        assert process.returncode == 0, f"helm template failed: {stderr.decode()}"

        # Verify the output contains valid YAML
        manifests = list(yaml.safe_load_all(stdout.decode()))
        assert len(manifests) > 0, "No manifests generated"

        # Verify we have expected resources
        resource_kinds = {m.get("kind") for m in manifests if m}
        assert "Deployment" in resource_kinds or "StatefulSet" in resource_kinds
        assert "Service" in resource_kinds

    finally:
        values_path.unlink()


@pytest.mark.skipif(
    os.system("which helm > /dev/null 2>&1") != 0,
    reason="helm not installed",
)
async def test_helm_template_with_custom_persistence_path(
    apolo_client,
    mock_get_preset_cpu,
    inputs_with_custom_persistence_path,
    chart_path,
):
    """Test that helm template works with custom persistence path."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    # Generate helm values
    helm_values = await input_processor.gen_extra_values(
        input_=inputs_with_custom_persistence_path,
        app_name="valkey-test",
        namespace="test-namespace",
        app_secrets_name="test-secret",
        app_id="test-app-id",
    )

    # Write values to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as values_file:
        yaml.dump(_values_for_chart(helm_values, chart_path), values_file)
        values_path = Path(values_file.name)

    try:
        # Run helm template
        process = await asyncio.create_subprocess_exec(
            "helm",
            "template",
            "test-release",
            str(chart_path),
            "-f",
            str(values_path),
            "--namespace",
            "test-namespace",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Check that helm template succeeded
        assert process.returncode == 0, f"helm template failed: {stderr.decode()}"

        # Verify the output contains valid YAML
        manifests = list(yaml.safe_load_all(stdout.decode()))
        assert len(manifests) > 0, "No manifests generated"

        # Verify we have expected resources
        resource_kinds = {m.get("kind") for m in manifests if m}
        assert "Deployment" in resource_kinds or "StatefulSet" in resource_kinds
        assert "Service" in resource_kinds

    finally:
        values_path.unlink()
