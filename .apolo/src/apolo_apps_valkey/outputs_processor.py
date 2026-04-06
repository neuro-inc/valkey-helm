import logging
import secrets
import typing as t

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379
_VALKEY_PREFIX = "valkey"


def _generate_secret_key() -> str:
    return f"{_VALKEY_PREFIX}.{secrets.token_hex(8)}"


def _define_host(app_instance_id: str) -> str:
    return f"{_VALKEY_PREFIX}-{app_instance_id}"


def _build_connection_info(host: str, secret_key: str) -> dict[str, t.Any]:
    return {
        "host": host,
        "port": VALKEY_PORT,
        "user": "",
        "password": ApoloSecret(key=secret_key),
    }


async def _build_uri(host: str, secret_key: str) -> str | None:
    try:
        api = RESPApi(
            host=host,
            port=VALKEY_PORT,
            password=ApoloSecret(key=secret_key),
        )
        return await api.resp_uri()
    except Exception:
        logger.exception("Failed to build RESP URI for host %r", host)
        return None


def _get_valkey_outputs(
    app_instance_id: str,
    secret_key: str,
) -> ValkeyAppOutputs:
    host = _define_host(app_instance_id)
    return ValkeyAppOutputs(
        connection=_build_connection_info(host, secret_key),
    )


class ValkeyAppOutputProcessor(BaseAppOutputsProcessor[ValkeyAppOutputs]):
    async def _generate_outputs(
        self,
        helm_values: dict[str, t.Any],  # kept for interface compatibility
        app_instance_id: str,
    ) -> ValkeyAppOutputs:
        secret_key = _generate_secret_key()
        return _get_valkey_outputs(app_instance_id, secret_key)

    async def generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
    ) -> dict[str, t.Any]:
        outputs = await self._generate_outputs(helm_values, app_instance_id)

        secret = outputs.connection.password if outputs.connection else None
        secret_key = secret.key if isinstance(secret, ApoloSecret) else None

        if not secret_key:
            secret_key = _generate_secret_key()

        host = _define_host(app_instance_id)
        uri = await _build_uri(host, secret_key)

        return {
            "uri": uri,
            "app_url": None,
            "raw": outputs.model_dump(),
        }
