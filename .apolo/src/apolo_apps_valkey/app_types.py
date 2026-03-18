import enum
from typing import Literal

from pydantic import ConfigDict, Field

from apolo_app_types import ServiceAPI
from apolo_app_types.helm.utils.storage import get_app_data_files_relative_path_url
from apolo_app_types.protocols.common import (
    AbstractAppFieldType,
    ApoloFilesPath,
    AppInputs,
    AppOutputs,
    AutoscalingHPA,
    Preset,
    SchemaExtraMetadata,
)
from apolo_app_types.protocols.common.ingress import BasicNetworkingConfig
from apolo_app_types.protocols.common.networking import WebApp


class ReplicaCount(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Fixed Replica Count",
            description="This option creates a fixed number of replicas "
            "with no autoscaling enabled.",
        ).as_json_schema_extra(),
    )
    replicas: int = Field(
        default=1,
        json_schema_extra=SchemaExtraMetadata(
            title="Replica Count",
            description="Number of replicas created for main application.",
        ).as_json_schema_extra(),
    )


class ValkeyVolume(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Persistent Storage",
            description=(
                "Configure persistent storage for the Valkey data directory. "
                "This volume stores encryption keys, instance logs, and source control "
                "assets. Persistence is recommended for production deployments."
            ),
        ).as_json_schema_extra(),
    )
    storage_mount: ApoloFilesPath = Field(
        default=ApoloFilesPath(
            path=str(
                get_app_data_files_relative_path_url(
                    app_type_name="valkey", app_name="valkey-app"
                )
            )
        ),
        json_schema_extra=SchemaExtraMetadata(
            title="Storage Mount Path",
            description=(
                "Select a platform storage path to mount for the Valkey data "
                "directory. This is required to persist critical data."
            ),
        ).as_json_schema_extra(),
    )


class MainApplicationConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Main Application Configuration",
            description="Configure the primary Valkey service that handles core "
            "data storage functionality, processes requests, and "
            "manages the core infrastructure.",
        ).as_json_schema_extra(),
    )
    preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Main Application preset",
            description="Select the resource preset used for the "
            "Valkey instance. "
            "Minimal resources: 0.1 CPU cores, 128 MiB memory.",
        ).as_json_schema_extra(),
    )
    replica_scaling: ReplicaCount | AutoscalingHPA = Field(
        default=ReplicaCount(replicas=1),
        json_schema_extra=SchemaExtraMetadata(
            title="Replicas",
            description="Choose a fixed number of replicas or enable autoscaling.",
        ).as_json_schema_extra(),
    )
    persistence: ValkeyVolume | None = Field(default=ValkeyVolume())


class WorkerConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Worker Configuration",
            description="Configure workers for distributed background job "
            "processing. Workers handle workflow execution tasks, enabling "
            "the main application to remain responsive by offloading "
            "computational work.",
        ).as_json_schema_extra(),
    )
    preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Worker preset",
            description="Select the resource preset used for the "
            "Worker instance. "
            "Minimal resources: 0.2 CPU cores, 128 MiB memory.",
        ).as_json_schema_extra(),
    )
    replicas: int = Field()


class WebhookConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Webhook Configuration",
            description="Configure dedicated webhook processing instances. "
            "Separating webhook handling allows dedicated resource allocation "
            "for webhook traffic without competing with core workflow execution.",
        ).as_json_schema_extra(),
    )
    preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Webhook preset",
            description="Select the resource preset used for the "
            "Webhook instance. "
            "Minimal resources: 0.1 CPU cores, 128 MiB memory.",
        ).as_json_schema_extra(),
    )
    replicas: int = Field()


class ValkeyArchitectureTypes(enum.StrEnum):
    STANDALONE = "standalone"
    REPLICATION = "replication"


class ValkeyArchitecture(AbstractAppFieldType):
    pass


class ValkeyStandaloneArchitecture(ValkeyArchitecture):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Standalone Mode",
            description="""This mode will deploy a standalone
                    Valkey StatefulSet. A single service will be exposed""",
        ).as_json_schema_extra(),
    )
    architecture_type: Literal[ValkeyArchitectureTypes.STANDALONE]


class ValkeyReplicationArchitecture(ValkeyArchitecture):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Replication Mode",
            description="""This mode will deploy a Valkey
                    primary StatefulSet and a Valkey replicas StatefulSet.
                    The replicas will be read-replicas of the primary and
                    two services will be exposed""",
        ).as_json_schema_extra(),
    )
    architecture_type: Literal[ValkeyArchitectureTypes.REPLICATION]
    replica_preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Replica Preset", description=""
        ).as_json_schema_extra(),
    )
    autoscaling: AutoscalingHPA | None = Field(
        default=None,
        json_schema_extra=SchemaExtraMetadata(
            title="Autoscaling",
            description="Enable Autoscaling and configure it.",
            is_advanced_field=True,
        ).as_json_schema_extra(),
    )


ValkeyArchs = ValkeyStandaloneArchitecture | ValkeyReplicationArchitecture


class ValkeyConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Valkey/Redis Configuration", description=""
        ).as_json_schema_extra(),
    )
    preset: Preset
    architecture: ValkeyArchs


class ValkeyAppInputs(AppInputs):
    main_app_config: MainApplicationConfig
    worker_config: WorkerConfig
    webhook_config: WebhookConfig
    valkey_config: ValkeyConfig
    networking: BasicNetworkingConfig = Field(
        default_factory=BasicNetworkingConfig,
        json_schema_extra=SchemaExtraMetadata(
            title="Networking Settings",
            description="Configure network access, HTTP authentication,"
            " and related connectivity options.",
        ).as_json_schema_extra(),
    )


class ValkeyAppOutputs(AppOutputs):
    """Outputs produced by Valkey app output processor.

    Add `uri` field so outputs serializers include the generated Redis/Valkey URI.
    """

    uri: str | None = Field(default=None)
    # Expose app_url for consumers that expect internal/external URLs. Keys
    # will be present even if values are None.
    app_url: ServiceAPI[WebApp] | None = Field(default=None)
