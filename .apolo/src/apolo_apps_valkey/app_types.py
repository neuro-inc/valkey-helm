import enum
from typing import Literal

from pydantic import ConfigDict, Field

from apolo_app_types import ContainerImage
from apolo_app_types.helm.utils.storage import get_app_data_files_relative_path_url
from apolo_app_types.protocols.common import (
    AbstractAppFieldType,
    ApoloFilesPath,
    ApoloSecret,
    AppInputs,
    AppOutputs,
    Preset,
    SchemaExtraMetadata,
)
from apolo_app_types.protocols.common.ingress import BasicNetworkingConfig
from apolo_app_types.protocols.resp_api import RESPApi


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
            description="Select the resource preset used for the Valkey instance. "
                        "Minimal resources: 0.1 CPU cores, 128 MiB memory.",
        ).as_json_schema_extra(),
    )
    docker_image_config: ContainerImage | None = Field(
        default=None,
        json_schema_extra=SchemaExtraMetadata(
            title="Docker Image Config",
            description="Override container image for Valkey.",
            is_advanced_field=True,
        ).as_json_schema_extra(),
    )
    persistence: ValkeyVolume | None = Field(default=ValkeyVolume())


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
            title="Replica Preset",
            description="Select the resource preset used for Valkey replica instances.",
        ).as_json_schema_extra(),
    )


ValkeyArchs = ValkeyStandaloneArchitecture | ValkeyReplicationArchitecture


class ValkeyConfig(AbstractAppFieldType):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra=SchemaExtraMetadata(
            title="Valkey/Redis Configuration",
            description=(
                "Top-level Valkey configuration. Configure the main application "
                "preset and deployment architecture (standalone or replication). "
                "When using replication, set replica presets and persistence "
                "options. These settings are used to generate the Helm values "
                "for deploying Valkey."
            ),
        ).as_json_schema_extra(),
    )
    preset: Preset = Field(
        ...,
        json_schema_extra=SchemaExtraMetadata(
            title="Main Application preset",
            description="Select the resource preset used for the Valkey instance. "
            "Minimal resources: 0.1 CPU cores, 128 MiB memory.",
        ).as_json_schema_extra(),
    )
    persistence: ValkeyVolume | None = Field(default=ValkeyVolume())
    architecture: ValkeyArchs


class ValkeyAppInputs(AppInputs):
    main_app_config: MainApplicationConfig
    valkey_config: ValkeyConfig
    networking: BasicNetworkingConfig = Field(
        default_factory=BasicNetworkingConfig,
        json_schema_extra=SchemaExtraMetadata(
            title="Networking Settings",
            description="Configure network access, HTTP authentication,"
            " and related connectivity options.",
        ).as_json_schema_extra(),
    )


class ValkeyConnectionInfo(AbstractAppFieldType):
    host: str
    port: int
    user: str = ""
    password: ApoloSecret

    @property
    def uri(self) -> str:
        creds = f"{self.user}:{self.password}" if self.user else f":{self.password}"
        return f"redis://{creds}@{self.host}:{self.port}"


class ValkeyAppOutputs(AppOutputs):
    redis: RESPApi | None = None
    connection: ValkeyConnectionInfo | None = None
