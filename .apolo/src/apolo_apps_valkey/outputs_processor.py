import logging
import typing as t

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379
VALKEY_USER = "default"
FULLNAME_PREFIX = "valkey"


def _get_host(helm_values: dict[str, t.Any], app_instance_id: str) -> str:
    fullname_override = helm_values.get("fullnameOverride")
    if isinstance(fullname_override, str) and fullname_override:
        return fullname_override

    return f"{FULLNAME_PREFIX}-{app_instance_id}"


def _resolve_auth(helm_values: dict[str, t.Any]) -> tuple[str, str]:
    connection_secret = helm_values.get("connectionSecret")
    if isinstance(connection_secret, dict):
        password = connection_secret.get("password")
        if isinstance(password, str) and password:
            return VALKEY_USER, password

    auth = helm_values.get("auth", {})
    acl_users = auth.get("aclUsers", {})
    default_user = acl_users.get(VALKEY_USER, {})
    password = default_user.get("password")
    username = default_user.get("username", VALKEY_USER)
    if isinstance(password, str):
        return username, password

    msg = (
        "Helm values must include connectionSecret.password or "
        "auth.aclUsers.default.password"
    )
    logger.error(msg)
    raise ValueError(msg)


async def get_valkey_outputs(
    helm_values: dict[str, t.Any], app_instance_id: str
) -> ValkeyAppOutputs:
    username, password = _resolve_auth(helm_values)
    host = _get_host(helm_values, app_instance_id)

    internal_api = RESPApi(
        host=host,
        port=VALKEY_PORT,
        user=username,
        password=ApoloSecret(key=password),
    )

    return ValkeyAppOutputs(
        redis=internal_api,
        connection={
            "host": host,
            "port": VALKEY_PORT,
            "user": username,
            "password": ApoloSecret(key=password),
        },
    )


class ValkeyAppOutputProcessor(BaseAppOutputsProcessor[ValkeyAppOutputs]):
    async def _generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
    ) -> ValkeyAppOutputs:
        return await get_valkey_outputs(helm_values, app_instance_id)
