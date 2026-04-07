import logging
import typing as t

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379
FULLNAME_PREFIX = "valkey"


def _get_host(helm_values: dict[str, t.Any], app_instance_id: str) -> str:
    fullname_override = helm_values.get("fullnameOverride")
    if isinstance(fullname_override, str) and fullname_override:
        return fullname_override

    return f"{FULLNAME_PREFIX}-{app_instance_id}"


def _resolve_auth(helm_values: dict[str, t.Any]) -> tuple[str, str | None]:
    connection_secret = helm_values.get("connectionSecret")
    if isinstance(connection_secret, dict):
        password = connection_secret.get("password")
        if isinstance(password, str) and password:
            return password, None

    auth = helm_values.get("auth")
    if isinstance(auth, dict):
        acl_users = auth.get("aclUsers")
        if isinstance(acl_users, dict):
            default_user = acl_users.get("default")
            if isinstance(default_user, dict):
                password = default_user.get("password")
                username = default_user.get("username", "default")
                if isinstance(password, str) and password:
                    return password, username

    msg = (
        "helm_values must include connectionSecret.password or "
        "auth.aclUsers.default.password"
    )
    raise ValueError(msg)


def _build_connection_info(
    host: str,
    password: str,
    username: str | None,
) -> dict[str, t.Any]:
    return {
        "host": host,
        "port": VALKEY_PORT,
        "user": username or "",
        "password": ApoloSecret(key=password),
    }


async def _build_uri(
    host: str,
    secret_key: str,
    username: str | None,
    client: t.Any = None,
) -> str | None:
    try:
        api = RESPApi(
            host=host,
            port=VALKEY_PORT,
            user=username or "",
            password=ApoloSecret(key=secret_key),
            client=client,
        )
        return await api.resp_uri()
    except Exception:
        logger.exception("Failed to build RESP URI for host %r", host)
        return None


def _get_valkey_outputs(
    host: str,
    password: str,
    username: str | None,
) -> ValkeyAppOutputs:
    return ValkeyAppOutputs(
        connection=_build_connection_info(host, password, username),
    )


class ValkeyAppOutputProcessor(BaseAppOutputsProcessor[ValkeyAppOutputs]):
    async def _generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
        client: t.Any = None,
    ) -> ValkeyAppOutputs:
        host = _get_host(helm_values, app_instance_id)
        password, username = _resolve_auth(helm_values)

        return _get_valkey_outputs(host, password, username)

    async def generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
        client: t.Any = None,  # type annotation added
    ) -> dict[str, t.Any]:
        host = _get_host(helm_values, app_instance_id)
        password, username = _resolve_auth(helm_values)

        outputs = _get_valkey_outputs(host, password, username)

        uri = await _build_uri(host, password, username, client=client)

        return {
            "uri": uri,
            "app_url": None,
            "raw": outputs.model_dump(),
        }
