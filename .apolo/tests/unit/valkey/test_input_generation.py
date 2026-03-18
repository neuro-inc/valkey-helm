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
    WebhookConfig,
    WorkerConfig,
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
        worker_config=WorkerConfig(preset=Preset(name="cpu-small"), replicas=2),
        webhook_config=WebhookConfig(preset=Preset(name="cpu-small"), replicas=1),
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
        app_name="n8n-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Check for expected keys in the output
    assert "apolo_app_id" in helm_params
    assert "ingress" in helm_params
    assert "podLabels" in helm_params
    assert "resources" in helm_params
    assert "service" in helm_params
    assert "labels" in helm_params
    assert "image" in helm_params
    assert "auth" in helm_params
    assert "extraEnv" in helm_params
    assert "secret" in helm_params

    # Check that application label is correct
    assert helm_params["labels"] == {"application": "valkey"}


async def test_valkey_replication_without_autoscaling(
    apolo_client, mock_get_preset_cpu
):
    """Test Valkey replication mode without autoscaling."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(preset=Preset(name="cpu-small")),
        worker_config=WorkerConfig(preset=Preset(name="cpu-small"), replicas=2),
        webhook_config=WebhookConfig(preset=Preset(name="cpu-small"), replicas=1),
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
        app_name="n8n-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Verify replication configuration
    replica_config = helm_params["replica"]
    assert replica_config["enabled"] is True
    assert replica_config["replicas"] == 2

    # Verify replica configuration
    # Only keys present: 'enabled', 'replicas', 'persistence'
    assert "enabled" in replica_config
    assert "replicas" in replica_config
    assert "persistence" in replica_config

    # Verify autoscaling is not present when not configured
    assert "autoscaling" not in replica_config


async def test_valkey_replication_with_autoscaling(apolo_client, mock_get_preset_cpu):
    """Test Valkey replication mode with autoscaling enabled."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(preset=Preset(name="cpu-small")),
        worker_config=WorkerConfig(preset=Preset(name="cpu-small"), replicas=2),
        webhook_config=WebhookConfig(preset=Preset(name="cpu-small"), replicas=1),
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
        app_name="n8n-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Verify replication configuration with autoscaling
    replica_config = helm_params["replica"]
    assert replica_config["enabled"] is True
    assert replica_config["replicas"] == 2

    # Verify autoscaling configuration
    assert "autoscaling" in replica_config
    hpa_config = replica_config["autoscaling"]["hpa"]
    assert hpa_config["enabled"] is True
    assert hpa_config["minReplicas"] == 2
    assert hpa_config["maxReplicas"] == 10
    assert hpa_config["targetCPU"] == 70
    assert hpa_config["targetMemory"] == 80


async def test_persistence_none_with_sqlite(apolo_client, mock_get_preset_cpu):
    """Test N8n values generation with persistence=None and SQLite database."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"), persistence=None
        ),
        worker_config=WorkerConfig(preset=Preset(name="cpu-small"), replicas=2),
        webhook_config=WebhookConfig(preset=Preset(name="cpu-small"), replicas=1),
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
        app_name="n8n-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Verify basic structure exists
    assert "podLabels" in helm_params
    assert "resources" in helm_params
    assert "service" in helm_params
    assert "labels" in helm_params
    assert "image" in helm_params
    assert "auth" in helm_params
    assert "extraEnv" in helm_params
    assert "secret" in helm_params


async def test_custom_persistence_path_with_sqlite(apolo_client, mock_get_preset_cpu):
    """Test N8n values generation with custom persistence path and SQLite."""
    input_processor = ValkeyAppChartValueProcessor(client=apolo_client)

    custom_path = "storage://test-cluster/custom/n8n/data"
    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            persistence=ValkeyVolume(storage_mount=ApoloFilesPath(path=custom_path)),
        ),
        worker_config=WorkerConfig(preset=Preset(name="cpu-small"), replicas=2),
        webhook_config=WebhookConfig(preset=Preset(name="cpu-small"), replicas=1),
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
        app_name="n8n-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Verify basic structure exists
    assert "podLabels" in helm_params
    assert "resources" in helm_params
    assert "service" in helm_params
    assert "labels" in helm_params
    assert "image" in helm_params
    assert "auth" in helm_params
    assert "extraEnv" in helm_params
    assert "secret" in helm_params
