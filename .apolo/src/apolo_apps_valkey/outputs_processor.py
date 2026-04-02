import logging
import typing as t
from inspect import iscoroutinefunction

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common.secrets_ import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs, ValkeyConnectionInfo


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379


async def get_valkey_outputs(
    helm_values: dict[str, t.Any],
    app_instance_id: str,
) -> ValkeyAppOutputs:
    """
    Create internal connections for standalone or replicated Valkey.
    """
    release_name = f"valkey-{app_instance_id}"

    pw_raw = helm_values.get("auth", {}).get("password")

    if isinstance(pw_raw, ApoloSecret):
        pw_field = pw_raw
    elif isinstance(pw_raw, dict):
        pw_field = ApoloSecret(**pw_raw)
    elif isinstance(pw_raw, str) and pw_raw:
        pw_field = ApoloSecret(key=pw_raw)
    else:
        pw_field = ApoloSecret(key="")

    internal_api = RESPApi(host=release_name, port=VALKEY_PORT, password=pw_raw or None)
    internal_conn = ValkeyConnectionInfo(
        host=release_name, port=VALKEY_PORT, user="", password=pw_field
    )
    return ValkeyAppOutputs(internal_connection=internal_conn, redis=internal_api)


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

        connections = [("internal", getattr(outputs, "internal_connection", None))]
        replicas = getattr(outputs, "replicas", [])
        connections.extend((f"replica_{i}", r) for i, r in enumerate(replicas))
        connections.append(("redis", getattr(outputs, "redis", None)))

        uri = None
        for name, conn in connections:
            if conn is None:
                continue
            try:
                resp_method = getattr(conn, "resp_uri", None)
                if resp_method is None or not callable(resp_method):
                    continue

                uri = (
                    await resp_method(None)
                    if iscoroutinefunction(resp_method)
                    else resp_method(None)
                )
                logger.info("Resolved Valkey URI from %s connection: %s", name, uri)
                break
            except Exception as e:
                logger.warning(
                    "Failed to resolve Valkey URI from %s connection: %s", name, e
                )
                continue

        raw = outputs.model_dump() if hasattr(outputs, "model_dump") else outputs
        return {"uri": uri, "app_url": None, "raw": raw}
