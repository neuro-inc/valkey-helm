import pytest
from apolo_app_types_fixtures.constants import (
    APP_ID,
    APP_SECRETS_NAME,
    DEFAULT_NAMESPACE,
)
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


@pytest.fixture
def basic_valkey_inputs():
    """Create basic ValkeyAppInputs for testing."""
    return ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
    )


async def test_valkey_values_generation(
    apolo_client, mock_get_preset_cpu, basic_valkey_inputs
):
    """Test Valkey values generation with basic inputs."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)
    helm_params = await input_processor.gen_extra_values(
        input_=basic_valkey_inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Basic platform-provided keys and their types
    assert "apolo_app_id" in helm_params
    assert isinstance(helm_params["apolo_app_id"], str)

    assert "ingress" in helm_params
    assert isinstance(helm_params["ingress"], dict)

    assert "podLabels" in helm_params
    assert isinstance(helm_params["podLabels"], dict)

    assert "resources" in helm_params
    assert isinstance(helm_params["resources"], dict)

    assert "service" in helm_params
    assert isinstance(helm_params["service"], dict)

    assert "labels" in helm_params
    assert isinstance(helm_params["labels"], dict)

    assert "image" in helm_params
    assert isinstance(helm_params["image"], dict)

    assert "auth" in helm_params
    assert isinstance(helm_params["auth"], dict)
    assert helm_params["auth"]["enabled"] is False

    assert "extraEnv" in helm_params
    assert isinstance(helm_params["extraEnv"], list)


async def test_no_connection_secret_by_default(
    apolo_client,
    mock_get_preset_cpu,
    basic_valkey_inputs,
):
    """Ensure gen_extra_values does not inject a connectionSecret unless requested."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)
    helm_params = await input_processor.gen_extra_values(
        input_=basic_valkey_inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # By default we do not add a connectionSecret block because auth stays off.
    assert "connectionSecret" not in helm_params
    assert helm_params["auth"] == {"enabled": False}

    # Check that application label is correct
    assert helm_params["labels"] == {"application": "valkey"}

    # fullnameOverride is set and follows expected prefix
    fullname = helm_params.get("fullnameOverride")
    assert isinstance(fullname, str)
    assert fullname.startswith("valkey-")

    # Ingress structure: hosts -> list of hosts each with 'paths' list
    ingress = helm_params["ingress"]
    assert "hosts" in ingress
    assert isinstance(ingress["hosts"], list)
    for host in ingress["hosts"]:
        assert isinstance(host, dict)
        assert "paths" in host
        assert isinstance(host["paths"], list)
        for p in host["paths"]:
            assert isinstance(p, str)

    # Service, image and auth basic values
    svc = helm_params["service"]
    assert svc.get("type") in {"ClusterIP", "LoadBalancer", "NodePort"}
    assert isinstance(svc.get("port"), int)
    assert "repository" in helm_params["image"]

    # Data storage block exists and is a dict
    assert "dataStorage" in helm_params
    assert isinstance(helm_params["dataStorage"], dict)


async def test_valkey_replication_without_autoscaling(
    apolo_client, mock_get_preset_cpu
):
    """Test Valkey replication mode without autoscaling."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyReplicationArchitecture(
                architecture_type=ValkeyArchitectureTypes.REPLICATION,
                replica_preset=Preset(name="cpu-small"),
            ),
        ),
        networking=BasicNetworkingConfig(),
    )

    helm_params = await input_processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Verify replication configuration
    replica_config = helm_params["replica"]
    assert replica_config["enabled"] is True
    assert replica_config["replicas"] == 2

    # Verify replica configuration structure
    assert "persistence" in replica_config
    assert isinstance(replica_config["persistence"], dict)
    assert "size" in replica_config["persistence"]
    assert "accessModes" in replica_config["persistence"]

    # Verify autoscaling is not present when not configured
    assert "autoscaling" not in replica_config


async def test_valkey_replication_with_autoscaling(apolo_client, mock_get_preset_cpu):
    """Test Valkey replication mode with autoscaling enabled."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
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

    helm_params = await input_processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    replica_config = helm_params["replica"]
    assert replica_config["enabled"] is True
    assert replica_config["replicas"] == 2

    # Ensure persistence block exists and contains expected fields
    assert "persistence" in replica_config
    assert isinstance(replica_config["persistence"], dict)
    assert "size" in replica_config["persistence"]
    assert "accessModes" in replica_config["persistence"]


async def test_persistence_defaults_are_enabled(apolo_client, mock_get_preset_cpu):
    """Test Helm values generation keeps the default persistence block."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )

    helm_params = await input_processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Verify basic structure exists
    assert "podLabels" in helm_params
    assert isinstance(helm_params["podLabels"], dict)
    assert "resources" in helm_params
    assert isinstance(helm_params["resources"], dict)
    assert "service" in helm_params
    assert isinstance(helm_params["service"], dict)
    assert "labels" in helm_params
    assert isinstance(helm_params["labels"], dict)
    assert "image" in helm_params
    assert isinstance(helm_params["image"], dict)
    assert "auth" in helm_params
    assert isinstance(helm_params["auth"], dict)
    assert "extraEnv" in helm_params
    assert isinstance(helm_params["extraEnv"], list)

    data_storage = helm_params["dataStorage"]
    assert data_storage["enabled"] is True
    assert data_storage["requestedSize"] == "1Gi"
    assert data_storage["volumeName"] == "valkey-data"
    assert data_storage["subPath"] is None
    assert data_storage["persistentVolumeClaimName"] is None


async def test_gen_extra_values_sets_default_image_tag(
    apolo_client, mock_get_preset_cpu, monkeypatch
):
    """`gen_extra_values` includes image.tag resolved from env/input/default."""
    monkeypatch.delenv("VALKEY_IMAGE_TAG", raising=False)

    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )

    helm = await input_processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # When no env var and no input server_version, the default tag is used
    assert helm.get("image", {}).get("tag") == "9.0.1"


async def test_gen_extra_values_prefers_env_image_tag(
    apolo_client, mock_get_preset_cpu, monkeypatch
):
    """`VALKEY_IMAGE_TAG` overrides the default image tag resolution."""
    monkeypatch.setenv("VALKEY_IMAGE_TAG", "9.9.9")

    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        valkey_config=ValkeyConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )

    helm = await input_processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    assert helm.get("image", {}).get("tag") == "9.9.9"
