import copy
import logging
import os
import secrets
import typing as t

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
DEFAULT_SERVER_VERSION = "9.0.1"
REPOSITORY_NAME = "valkey/valkey"
VALKEY_PORT = 6379
SERVICE_TYPE = "ClusterIP"
PULL_POLICY = "IfNotPresent"
DATA_VOLUME_NAME = "valkey-data"
AUTH_DEFAULT_PERMISSIONS = "~* &* +@all"


def _generate_secret_key() -> str:
    return f"{FULLNAME_PREFIX}-{secrets.token_hex(8)}"


def _resolve_image_tag(input_: ValkeyAppInputs) -> str:
    return (
        os.getenv("VALKEY_IMAGE_TAG")
        or getattr(input_.main_app_config, "server_version", None)
        or DEFAULT_SERVER_VERSION
    )


def _build_optional_values(extra_values: dict[str, t.Any]) -> dict[str, t.Any]:
    defaults = {
        "extraEnv": [],
        "podLabels": {},
        "podAnnotations": {},
        "commonLabels": {},
        "resources": {},
        "tolerations": [],
        "affinity": {},
        "priorityClassName": "",
    }
    return {k: extra_values.get(k, v) for k, v in defaults.items()}


def _build_persistence(input_: ValkeyAppInputs) -> dict[str, t.Any]:
    persistence = input_.main_app_config.persistence
    if not persistence:
        return {"enabled": False}

    return {
        "enabled": True,
        "requestedSize": getattr(persistence, "size", "1Gi"),
        "volumeName": DATA_VOLUME_NAME,
        "subPath": getattr(persistence, "subPath", None),
        "persistentVolumeClaimName": getattr(
            persistence, "persistentVolumeClaimName", None
        ),
    }


def _build_replication(config: t.Any) -> dict[str, t.Any]:
    arch = config.architecture

    if arch.architecture_type != ValkeyArchitectureTypes.REPLICATION:
        return {"enabled": False}

    return {
        "enabled": True,
        "replicas": getattr(arch, "replicas", 2),
        "persistence": {
            "size": getattr(arch, "persistence_size", "1Gi"),
            "accessModes": getattr(arch, "persistence_access_modes", ["ReadWriteOnce"]),
        },
    }


def _build_ingress(extra_values: dict[str, t.Any]) -> dict[str, t.Any]:
    ingress = copy.deepcopy(extra_values["ingress"])

    for host in ingress.get("hosts", []):
        host["paths"] = [p["path"] for p in host.get("paths", [])]

    return ingress


def _build_auth() -> dict[str, t.Any]:
    return {
        "enabled": True,
        "aclUsers": {
            "default": {
                "permissions": AUTH_DEFAULT_PERMISSIONS,
                "password": _generate_secret_key(),
            }
        },
    }


class ValkeyAppChartValueProcessor(BaseChartValueProcessor[ValkeyAppInputs]):
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
            app_type=AppType.Valkey,
            namespace=namespace,
            ingress_http=input_.networking.ingress_http,
        )

        helm_values: dict[str, t.Any] = {
            "apolo_app_id": extra_values["apolo_app_id"],
            "ingress": _build_ingress(extra_values),
            "fullnameOverride": f"{FULLNAME_PREFIX}-{app_id[:16]}",
            "dataStorage": _build_persistence(input_),
            "replica": _build_replication(input_.main_app_config),
            "image": {
                "repository": REPOSITORY_NAME,
                "pullPolicy": PULL_POLICY,
                "tag": _resolve_image_tag(input_),
            },
            "service": {
                "type": SERVICE_TYPE,
                "port": VALKEY_PORT,
                "annotations": {},
            },
            "auth": _build_auth(),
            "labels": {"application": "valkey"},
        }

        helm_values.update(_build_optional_values(extra_values))

        return helm_values
