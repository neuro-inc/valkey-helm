import logging
import typing as t
from typing import cast

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379
SECRET_KEY = "valkey.password"


def build_connection_info(
    host: str | None,
    password: str | None,
) -> dict[str, t.Any] | None:
    if not host or not password:
        return None

    return {
        "host": host,
        "port": VALKEY_PORT,
        "user": "",
        "password": {"key": SECRET_KEY},
    }


async def build_uri(
    host: str | None,
    password: str | None,
) -> str | None:
    if not host or not password:
        return None

    try:
        api = RESPApi(
            host=host,
            port=VALKEY_PORT,
            password=cast(
                ApoloSecret,
                {"key": SECRET_KEY, "value": password},
            ),
        )

        return await api.resp_uri()

    except Exception:
        logger.exception("Failed to build RESP URI")
        return None


async def get_valkey_outputs(
    helm_values: dict[str, t.Any],
    app_instance_id: str,
) -> ValkeyAppOutputs:
    release_name = f"valkey-{app_instance_id}"
    internal_host = release_name

    password: str | None = helm_values.get("auth", {}).get("password")

    external_host: str | None = None
    if helm_values.get("service", {}).get("type") == "LoadBalancer":
        external_host = helm_values.get("service", {}).get("externalIP")

    return ValkeyAppOutputs(
        internal_connection=build_connection_info(internal_host, password),
        external_connection=build_connection_info(external_host, password),
    )


class ValkeyAppOutputProcessor(BaseAppOutputsProcessor[ValkeyAppOutputs]):
    async def _generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
    ) -> ValkeyAppOutputs:
        return await get_valkey_outputs(helm_values, app_instance_id)

    async def generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
    ) -> dict[str, t.Any]:
        outputs = await self._generate_outputs(helm_values, app_instance_id)

        password: str | None = helm_values.get("auth", {}).get("password")
        release_name = f"valkey-{app_instance_id}"
        internal_host = release_name

        external_host: str | None = None
        if helm_values.get("service", {}).get("type") == "LoadBalancer":
            external_host = helm_values.get("service", {}).get("externalIP")

        uri = await build_uri(internal_host, password)
        if not uri:
            uri = await build_uri(external_host, password)

        return {
            "uri": uri,
            "app_url": None,
            "raw": outputs.model_dump(),
        }
