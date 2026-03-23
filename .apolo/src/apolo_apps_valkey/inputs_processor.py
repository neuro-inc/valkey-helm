import logging
import typing as t
from typing import Any

from apolo_app_types.app_types import AppType
from apolo_app_types.helm.apps.base import BaseChartValueProcessor
from apolo_app_types.helm.apps.common import gen_extra_values
from apolo_apps_valkey.app_types import (
    ValkeyAppInputs,
    ValkeyArchitectureTypes,
)


logger = logging.getLogger(__name__)

# Chart/name constants
FULLNAME_PREFIX = "valkey"


class ValkeyAppChartValueProcessor(BaseChartValueProcessor[ValkeyAppInputs]):
    _port: int = 6379

    def __init__(
        self,
        client: Any,
        *args: t.Any,
        **kwargs: t.Any,
    ):
        super().__init__(client, *args, **kwargs)

    async def get_redis_values(
        self, input_: ValkeyAppInputs, app_id: str
    ) -> dict[str, t.Any]:
        config = input_.valkey_config
        values = {
            # Provide a stable fullnameOverride used by the chart. Use the
            # `FULLNAME_PREFIX` constant to avoid accidental copy/paste from
            # other applications.
            "fullnameOverride": f"{FULLNAME_PREFIX}-{app_id[:16]}",
            "global": {"security": {"allowInsecureImages": True}},
            "image": {"repository": "bitnamilegacy/valkey"},
            "auth": {"enabled": False},
            "architecture": str(config.architecture.architecture_type.value),
            "primary": {},
        }

        # Replica mode (replication architecture) — do not generate any autoscaling
        if config.architecture.architecture_type == ValkeyArchitectureTypes.REPLICATION:
            replica_config: dict[str, t.Any] = {}
            replica_config["enabled"] = True
            replica_config.setdefault("persistence", {})
            if not replica_config["persistence"].get("size"):
                replica_config["persistence"]["size"] = "1Gi"
            if not replica_config["persistence"].get("accessModes"):
                replica_config["persistence"]["accessModes"] = ["ReadWriteOnce"]
            replica_config.setdefault("replicas", 2)
            values["replica"] = replica_config
        return values

    async def gen_extra_values(
        self,
        input_: ValkeyAppInputs,
        app_name: str,
        namespace: str,
        app_id: str,
        app_secrets_name: str,
        *args: t.Any,
        **kwargs: t.Any,
    ) -> dict[str, t.Any]:
        extra_values = await gen_extra_values(
            app_id=app_id,
            # Attempt to select an appropriate AppType for Valkey. Different
            # versions of the platform may expose different enum members
            # (e.g. VALKEY, Valkey, VALKEY_APP). Fall back to N8n only if a
            # Valkey-like member is not present to preserve backwards
            # compatibility with older fixtures.
            app_type=(
                getattr(AppType, "VALKEY", None)
                or getattr(AppType, "Valkey", None)
                or getattr(AppType, "VALKEY_APP", None)
                or (AppType.N8n if hasattr(AppType, "N8n") else list(AppType)[0])
            ),
            apolo_client=self.client,
            preset_type=input_.main_app_config.preset,
            namespace=namespace,
            ingress_http=input_.networking.ingress_http,
        )

        helm_values = {
            "apolo_app_id": extra_values["apolo_app_id"],
            "ingress": extra_values["ingress"],
            # `extraEnv` commonly used by charts to inject platform-provided
            # environment variables; include it from extra_values when
            # available so unit tests and charts relying on it behave as
            # expected.
            "extraEnv": extra_values.get("extraEnv", []),
            "podLabels": extra_values.get("podLabels", {}),
            "podAnnotations": extra_values.get("podAnnotations", {}),
            "commonLabels": extra_values.get("commonLabels", {}),
            "resources": extra_values.get("resources", {}),
            "tolerations": extra_values.get("tolerations", []),
            "affinity": extra_values.get("affinity", {}),
            "priorityClassName": extra_values.get("priorityClassName", ""),
        }

        helm_values["fullnameOverride"] = f"{FULLNAME_PREFIX}-{app_id[:16]}"

        if input_.main_app_config.persistence:
            persistence = input_.main_app_config.persistence
            helm_values["dataStorage"] = {
                "enabled": True,
                "requestedSize": persistence.size
                if hasattr(persistence, "size")
                else "1Gi",
                "volumeName": "valkey-data",
                "subPath": getattr(persistence, "subPath", None),
                "persistentVolumeClaimName": getattr(
                    persistence, "persistentVolumeClaimName", None
                ),
            }
        else:
            helm_values["dataStorage"] = {"enabled": False}

        config = input_.valkey_config
        # Replica mode (replication architecture) — do not generate any autoscaling
        if config.architecture.architecture_type == ValkeyArchitectureTypes.REPLICATION:
            replica_config = {
                "enabled": True,
                "replicas": getattr(config.architecture, "replicas", 2),
                "persistence": {
                    "size": getattr(config.architecture, "persistence_size", "1Gi"),
                    "accessModes": getattr(
                        config.architecture,
                        "persistence_access_modes",
                        ["ReadWriteOnce"],
                    ),
                },
            }
            helm_values["replica"] = replica_config
        else:
            helm_values["replica"] = {"enabled": False}

        helm_values["image"] = {
            "repository": "bitnamilegacy/valkey",
            "pullPolicy": "IfNotPresent",
        }

        helm_values["service"] = {
            "type": "ClusterIP",
            "port": 6379,
            "annotations": {},
        }

        helm_values["auth"] = {"enabled": False}
        helm_values["labels"] = {"application": "valkey"}

        ingress = extra_values["ingress"]
        for i, host in enumerate(ingress["hosts"]):
            paths = host["paths"]
            ingress["hosts"][i]["paths"] = [p["path"] for p in paths]

        return helm_values
