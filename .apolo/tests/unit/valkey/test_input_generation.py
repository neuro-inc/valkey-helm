import pytest
from apolo_app_types_fixtures.constants import (
    APP_ID,
    APP_SECRETS_NAME,
    DEFAULT_NAMESPACE,
)
from apolo_apps_valkey.app_types import (
    MainApplicationConfig,
    ValkeyAppInputs,
    ValkeyArchitectureTypes,
    ValkeyConfig,
    ValkeyReplicationArchitecture,
    ValkeyStandaloneArchitecture,
    ValkeyVolume,
)
from apolo_apps_valkey.inputs_processor import ValkeyAppChartValueProcessor

from apolo_app_types.protocols.common import ApoloFilesPath, AutoscalingHPA, Preset
from apolo_app_types.protocols.common.ingress import BasicNetworkingConfig


@pytest.fixture
def basic_valkey_inputs():
    """Create basic ValkeyAppInputs for testing."""
    return ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"), persistence=None
        ),
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

    assert "extraEnv" in helm_params
    assert isinstance(helm_params["extraEnv"], list)


async def test_no_connection_secret_by_default(apolo_client, mock_get_preset_cpu, basic_valkey_inputs):
    """Ensure gen_extra_values does not inject a connectionSecret unless requested."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)
    helm_params = await input_processor.gen_extra_values(
        input_=basic_valkey_inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # By default we do not add a connectionSecret block; it should only appear
    # when the caller supplies it (or when inline auth is configured).
    assert "connectionSecret" not in helm_params

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
        main_app_config=MainApplicationConfig(preset=Preset(name="cpu-small")),
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
        main_app_config=MainApplicationConfig(preset=Preset(name="cpu-small")),
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


async def test_persistence_none_with_sqlite(apolo_client, mock_get_preset_cpu):
    """Test Helm values generation with persistence=None and SQLite database."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"), persistence=None
        ),
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


async def test_custom_persistence_path_with_sqlite(apolo_client, mock_get_preset_cpu):
    """Test N8n values generation with custom persistence path and SQLite."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    custom_path = "storage://test-cluster/custom/n8n/data"
    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            persistence=ValkeyVolume(storage_mount=ApoloFilesPath(path=custom_path)),
        ),
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
