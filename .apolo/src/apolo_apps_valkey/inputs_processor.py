import logging
import typing as t
from typing import Any


try:
    import apolo_sdk
except Exception:  # pragma: no cover - optional dependency in test env
    apolo_sdk = None  # type: ignore


from apolo_app_types.app_types import AppType
from apolo_app_types.helm.apps.base import BaseChartValueProcessor
from apolo_app_types.helm.apps.common import (
    gen_extra_values,
)
from apolo_app_types.protocols.common import (
    AutoscalingHPA,
)
from apolo_apps_valkey.app_types import (
    ValkeyAppInputs,
    ValkeyArchitectureTypes,
)


logger = logging.getLogger(__name__)


class ValkeyAppChartValueProcessor(BaseChartValueProcessor[ValkeyAppInputs]):
    _port: int = 6379

    def __init__(
        self,
        client: Any,
        *args: t.Any,
        **kwargs: t.Any,
    ):
        super().__init__(client, *args, **kwargs)

    def get_extra_env(
        self,
        input_: ValkeyAppInputs,
        app_secrets_name: str,
        app_id: str,
        webhook_url: str | None = None,
    ) -> dict[str, t.Any]:
        envs = {}
        if webhook_url:
            envs["WEBHOOK_URL"] = {"value": webhook_url}
            envs["EXECUTIONS_MODE"] = {"value": "queue"}
            envs["QUEUE_BULL_REDIS_HOST"] = {
                "value": f"n8n-{app_id[:16]}-valkey-primary"
            }
            envs["QUEUE_BULL_REDIS_TLS"] = {"value": "false"}
        return envs

    def get_autoscaling_values(self, autoscaling: AutoscalingHPA) -> dict[str, t.Any]:
        return {
            "enabled": True,
            "minReplicas": autoscaling.min_replicas,
            "maxReplicas": autoscaling.max_replicas,
            "targetCPUUtilizationPercentage": (
                autoscaling.target_cpu_utilization_percentage
            ),
            "targetMemoryUtilizationPercentage": (
                autoscaling.target_memory_utilization_percentage
            ),
        }

    def is_webhook_enabled(self, input_: ValkeyAppInputs) -> bool:
        return input_.webhook_config.replicas > 0

    async def get_redis_values(
        self, input_: ValkeyAppInputs, app_id: str
    ) -> dict[str, t.Any]:
        config = input_.valkey_config
        values = {
            "fullnameOverride": f"n8n-{app_id[:16]}-valkey",
            "global": {"security": {"allowInsecureImages": True}},
            "image": {"repository": "bitnamilegacy/valkey"},
            "auth": {"enabled": False},
            "enabled": self.is_webhook_enabled(input_),
            "architecture": str(config.architecture.architecture_type.value),
            "primary": {},
        }

        # Type check for autoscaling attribute
        if (
            hasattr(config.architecture, "autoscaling")
            and config.architecture.architecture_type
            == ValkeyArchitectureTypes.REPLICATION
        ):
            replica_config: dict[str, t.Any] = {}
            autoscaling = config.architecture.autoscaling
            if autoscaling is not None:
                replica_config["autoscaling"] = {
                    "enabled": True,
                    "hpa": {
                        "enabled": True,
                        "minReplicas": autoscaling.min_replicas,
                        "maxReplicas": autoscaling.max_replicas,
                        "targetCPU": (autoscaling.target_cpu_utilization_percentage),
                        "targetMemory": (
                            autoscaling.target_memory_utilization_percentage
                        ),
                    },
                }
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
            app_type=AppType.N8n,
            apolo_client=self.client,
            preset_type=input_.main_app_config.preset,
            namespace=namespace,
            ingress_http=input_.networking.ingress_http,
        )

        helm_values = {
            "apolo_app_id": extra_values["apolo_app_id"],
            "ingress": extra_values["ingress"],
            "podLabels": extra_values.get("podLabels", {}),
            "podAnnotations": extra_values.get("podAnnotations", {}),
            "commonLabels": extra_values.get("commonLabels", {}),
            "resources": extra_values.get("resources", {}),
            "tolerations": extra_values.get("tolerations", []),
            "affinity": extra_values.get("affinity", {}),
            "priorityClassName": extra_values.get("priorityClassName", ""),
        }

        helm_values["fullnameOverride"] = f"n8n-{app_id[:16]}-valkey"

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
        # Type check for autoscaling attribute
        if (
            hasattr(config.architecture, "autoscaling")
            and config.architecture.architecture_type
            == ValkeyArchitectureTypes.REPLICATION
        ):
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
            autoscaling = config.architecture.autoscaling
            if autoscaling is not None:
                replica_config["autoscaling"] = {
                    "enabled": True,
                    "hpa": {
                        "enabled": True,
                        "minReplicas": autoscaling.min_replicas,
                        "maxReplicas": autoscaling.max_replicas,
                        "targetCPU": (autoscaling.target_cpu_utilization_percentage),
                        "targetMemory": (
                            autoscaling.target_memory_utilization_percentage
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

        webhook_url = None
        ingress = extra_values["ingress"]
        for i, host in enumerate(ingress["hosts"]):
            paths = host["paths"]
            ingress["hosts"][i]["paths"] = [p["path"] for p in paths]
            if self.is_webhook_enabled(input_):
                webhook_url = "https://" + host["host"]

        extra_env = self.get_extra_env(
            input_=input_,
            app_secrets_name=app_secrets_name,
            app_id=app_id,
            webhook_url=webhook_url,
        )
        helm_values["extraEnv"] = extra_env

        return helm_values
