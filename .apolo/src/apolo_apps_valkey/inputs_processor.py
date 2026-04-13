import copy
import logging
import os
import random
import string
import typing as t

import apolo_sdk

from apolo_app_types.app_types import AppType
from apolo_app_types.helm.apps.base import BaseChartValueProcessor
from apolo_app_types.helm.apps.common import (
    gen_extra_values as _gen_common_extra_values,
)
from apolo_app_types.outputs.utils.apolo_secrets import get_apolo_secret
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
PASSWORD_CHAR_POOL = string.ascii_letters + string.digits
PASSWORD_DEFAULT_LENGTH = 12
PASSWORD_MIN_LENGTH = 4


def _generate_password(length: int = PASSWORD_DEFAULT_LENGTH) -> str:
    if length < PASSWORD_MIN_LENGTH:
        err_msg = f"Password length must be at least {PASSWORD_MIN_LENGTH}"
        raise ValueError(err_msg)

    return "".join([random.choice(PASSWORD_CHAR_POOL) for _ in range(length)])


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


async def _build_auth(app_id: str) -> dict[str, t.Any]:
    try:
        keycloak_password = await get_apolo_secret(
            app_instance_id=app_id, key=f"{FULLNAME_PREFIX}-password"
        )
    except apolo_sdk.ResourceNotFound:
        keycloak_password = _generate_password()

    return {
        "enabled": True,
        "aclUsers": {
            "default": {
                "permissions": AUTH_DEFAULT_PERMISSIONS,
                "password": keycloak_password,
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
            "auth": await _build_auth(app_id),
            "labels": {"application": "valkey"},
        }

        helm_values.update(_build_optional_values(extra_values))

        return helm_values
