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
    ValkeyReplicationArchitecture,
    ValkeyStandaloneArchitecture,
)
from apolo_apps_valkey.inputs_processor import ValkeyAppChartValueProcessor

from apolo_app_types.protocols.common import AutoscalingHPA, Preset
from apolo_app_types.protocols.common.ingress import BasicNetworkingConfig


@pytest.fixture
def basic_valkey_inputs():
    return ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
            persistence=None,
        ),
        networking=BasicNetworkingConfig(),
    )


async def test_valkey_values_generation(
    apolo_client, mock_get_preset_cpu, basic_valkey_inputs
):
    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    helm = await processor.gen_extra_values(
        input_=basic_valkey_inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    # Core structure
    assert isinstance(helm.get("apolo_app_id"), str)
    assert isinstance(helm.get("ingress"), dict)
    assert isinstance(helm.get("podLabels"), dict)
    assert isinstance(helm.get("resources"), dict)
    assert isinstance(helm.get("service"), dict)
    assert isinstance(helm.get("labels"), dict)
    assert isinstance(helm.get("image"), dict)
    assert isinstance(helm.get("auth"), dict)
    assert isinstance(helm.get("extraEnv"), list)

    # Image
    assert helm["image"]["repository"] == "valkey/valkey"
    assert "tag" in helm["image"]

    # Auth structure
    auth = helm["auth"]
    assert auth["enabled"] is True
    assert "aclUsers" in auth
    assert "default" in auth["aclUsers"]
    assert "password" in auth["aclUsers"]["default"]

    # Data storage (persistence disabled)
    storage = helm["dataStorage"]
    assert storage["enabled"] is False


async def test_no_connection_secret_by_default(
        apolo_client, mock_get_preset_cpu, basic_valkey_inputs
):
    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    helm = await processor.gen_extra_values(
        input_=basic_valkey_inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    assert "connectionSecret" not in helm
    assert helm["labels"] == {"application": "valkey"}

    fullname = helm.get("fullnameOverride")
    assert isinstance(fullname, str)
    assert fullname.startswith("valkey-")

    # Ingress validation (more defensive)
    ingress = helm["ingress"]
    assert isinstance(ingress.get("hosts"), list)

    for host in ingress["hosts"]:
        assert isinstance(host, dict)
        assert isinstance(host.get("paths"), list)
        for p in host["paths"]:
            assert isinstance(p, str)

    # Service sanity
    svc = helm["service"]
    assert svc["type"] in {"ClusterIP", "LoadBalancer", "NodePort"}
    assert isinstance(svc["port"], int)


async def test_valkey_replication_without_autoscaling(
    apolo_client, mock_get_preset_cpu
):
    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyReplicationArchitecture(
                architecture_type=ValkeyArchitectureTypes.REPLICATION,
                replica_preset=Preset(name="cpu-small"),
            ),
        ),
        networking=BasicNetworkingConfig(),
    )

    helm = await processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    replica = helm["replica"]
    assert replica["enabled"] is True
    assert replica["replicas"] == 2

    # Persistence block
    persistence = replica["persistence"]
    assert isinstance(persistence, dict)
    assert "size" in persistence
    assert "accessModes" in persistence

    # No autoscaling
    assert "autoscaling" not in replica


async def test_valkey_replication_with_autoscaling(apolo_client, mock_get_preset_cpu):
    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
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

    helm = await processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    replica = helm["replica"]
    assert replica["enabled"] is True
    assert replica["replicas"] == 2

    # Persistence still exists
    assert "persistence" in replica
    assert isinstance(replica["persistence"], dict)


async def test_persistence_none(apolo_client, mock_get_preset_cpu):
    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
            persistence=None,
        ),
        networking=BasicNetworkingConfig(),
    )

    helm = await processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    storage = helm["dataStorage"]
    assert storage["enabled"] is False


async def test_persistence_enabled(apolo_client, mock_get_preset_cpu):
    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
            # persistence defaults to ValkeyVolume() which enables storage
        ),
        networking=BasicNetworkingConfig(),
    )

    helm = await processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    storage = helm["dataStorage"]
    assert storage["enabled"] is True
    assert "requestedSize" in storage
    assert storage["volumeName"] == "valkey-data"


async def test_gen_extra_values_sets_default_image_tag(
    apolo_client, mock_get_preset_cpu, monkeypatch
):
    monkeypatch.delenv("VALKEY_IMAGE_TAG", raising=False)

    processor = ValkeyAppChartValueProcessor(client=apolo_client)

    inputs = ValkeyAppInputs(
        main_app_config=MainApplicationConfig(
            preset=Preset(name="cpu-small"),
            architecture=ValkeyStandaloneArchitecture(
                architecture_type=ValkeyArchitectureTypes.STANDALONE
            ),
        ),
        networking=BasicNetworkingConfig(),
    )

    helm = await processor.gen_extra_values(
        input_=inputs,
        app_name="valkey-app",
        namespace=DEFAULT_NAMESPACE,
        app_secrets_name=APP_SECRETS_NAME,
        app_id=APP_ID,
    )

    assert helm["image"]["tag"] == "9.0.1"
