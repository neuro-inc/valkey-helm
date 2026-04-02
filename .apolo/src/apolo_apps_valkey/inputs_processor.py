import logging
import os
import typing as t
from typing import Any

import httpx

from apolo_app_types.app_types import AppType
from apolo_app_types.helm.apps.base import BaseChartValueProcessor
from apolo_app_types.helm.apps.common import (
    gen_extra_values as _gen_common_extra_values,
)
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
        server_ver = getattr(input_.main_app_config, "server_version", None)

        values: dict[str, t.Any] = {
            # Provide a stable fullnameOverride used by the chart. Use the
            # `FULLNAME_PREFIX` constant to avoid accidental copy/paste from
            # other applications.
            "fullnameOverride": f"{FULLNAME_PREFIX}-{app_id[:16]}",
            "global": {"security": {"allowInsecureImages": True}},
            "image": {"repository": "valkey/valkey"},
            "auth": {"enabled": False},
            "architecture": str(config.architecture.architecture_type.value),
            "primary": {},
        }

        if server_ver:
            values["image"]["tag"] = server_ver

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
        # Optional check of image tag when enabled via env var
        if server_ver and os.environ.get("VALKEY_CHECK_IMAGE_TAG") == "1":
            await _maybe_check_image_tag(str(values["image"]["repository"]), server_ver)

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
        extra_values = await _gen_common_extra_values(
            apolo_client=self.client,
            preset_type=input_.main_app_config.preset,
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
            namespace=namespace,
            ingress_http=input_.networking.ingress_http,
        )

        helm_values: dict[str, t.Any] = {
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

        # If a specific server_version (image tag) is provided via inputs,
        # include it in Helm values so the chart deploys the pinned image.
        server_ver = getattr(input_.main_app_config, "server_version", None)

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
            "repository": "valkey/valkey",
            "pullPolicy": "IfNotPresent",
        }
        if server_ver:
            helm_values["image"]["tag"] = server_ver
            if os.environ.get("VALKEY_CHECK_IMAGE_TAG") == "1":
                await _maybe_check_image_tag(
                    str(helm_values["image"]["repository"]), server_ver
                )

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


async def _sync_check_dockerhub_tag(repo: str, tag: str) -> bool:
    """Async helper: check Docker Hub API for a specific tag using httpx.

    Returns True if tag exists, False otherwise. This is intentionally
    best-effort and should not raise on network errors.
    """
    try:
        parts = repo.split("/")
        if len(parts) == 1:
            namespace = "library"
            name = parts[0]
        else:
            namespace, name = parts[0], parts[1]
        url = f"https://hub.docker.com/v2/repositories/{namespace}/{name}/tags/{tag}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=5.0)
            # 200 -> exists, 404 -> not found, others -> treat as not found
            return r.status_code == 200
    except httpx.HTTPStatusError:
        return False
    except Exception:
        # Best-effort: don't raise on network errors
        return False


async def _maybe_check_image_tag(repo: str, tag: str) -> None:
    """Asynchronous entrypoint to run the sync tag check in executor.

    Logs a warning if the tag doesn't exist. No exceptions are raised.
    """
    ok = await _sync_check_dockerhub_tag(repo, tag)
    if not ok:
        logger.warning("Valkey image tag not found on Docker Hub: %s:%s", repo, tag)
