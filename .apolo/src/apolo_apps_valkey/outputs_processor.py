import logging
import typing as t

from apolo_app_types.clients.kube import get_services
from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.outputs.common import INSTANCE_LABEL
from apolo_app_types.protocols.common import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379
VALKEY_USER = "default"
FULLNAME_PREFIX = "valkey"


async def _get_service_endpoints(
    release_name: str, app_instance_id: str
) -> tuple[str, int]:
    services = await get_services(
        match_labels={
            "application": release_name,
            INSTANCE_LABEL: app_instance_id,
        }
    )

    host = ""
    port = 0
    for service in services:
        service_name = service["metadata"]["name"]
        service_host = f"{service_name}.{service['metadata']['namespace']}"
        service_port = int(service["spec"]["ports"][0]["port"])  # Ensure int

        if service_name.startswith("valkey"):
            host, port = service_host, service_port
            break

    if host == "" or port == 0:
        msg = "Could not find Valkey service endpoints."
        raise Exception(msg)

    return host, port


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
    release_name = "valkey"

    try:
        host, port = await _get_service_endpoints(release_name, app_instance_id)
    except Exception as e:
        msg = f"Could not find Valkey services: {e}"
        raise Exception(msg) from e

    username, password = _resolve_auth(helm_values)

    internal_api = RESPApi(
        host=host,
        port=port,
        user=username,
        password=ApoloSecret(key=password),
    )

    return ValkeyAppOutputs(
        redis=internal_api,
        connection={
            "host": host,
            "port": port,
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
