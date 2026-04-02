import logging
import typing as t
from typing import cast

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common import ApoloSecret
from apolo_app_types.protocols.resp_api import RESPApi
from apolo_apps_valkey.app_types import ValkeyAppOutputs


logger = logging.getLogger(__name__)

VALKEY_PORT = 6379


async def get_valkey_outputs(
    helm_values: dict[str, t.Any],
    app_instance_id: str,
) -> ValkeyAppOutputs:
    release_name = f"valkey-{app_instance_id}"

    # внутрішній доступ
    internal_host = f"{release_name}"

    password = helm_values.get("auth", {}).get("password")

    internal_api = None
    if password:
        # ApoloSecret is a typing-only TypedDict/Protocol — do not call it.
        internal_api = RESPApi(
            host=internal_host,
            port=VALKEY_PORT,
            password=cast(ApoloSecret, {"name": "valkey.password", "value": password}),
        )

    # 👉 external доступ (якщо LoadBalancer)
    external_api = None
    if helm_values.get("service", {}).get("type") == "LoadBalancer":
        external_host = helm_values.get("service", {}).get("externalIP")

        if external_host:
            external_api = RESPApi(
                host=external_host,
                port=VALKEY_PORT,
                password=cast(
                    ApoloSecret, {"name": "valkey.password", "value": password}
                ),
            )

    return ValkeyAppOutputs(
        internal_connection=internal_api,
        external_connection=external_api,
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

        internal = getattr(outputs, "internal_connection", None)
        external = getattr(outputs, "external_connection", None)

        uri = None
        if internal is not None:
            try:
                uri = internal.resp_uri
            except Exception:
                uri = None
        elif external is not None:
            try:
                uri = external.resp_uri
            except Exception:
                uri = None

        # Ensure `raw` is JSON-serializable: prefer Pydantic `model_dump`
        # or `dict` when available
        def _to_primitive(obj: t.Any) -> t.Any:
            try:
                if hasattr(obj, "model_dump") and callable(obj.model_dump):
                    return obj.model_dump()
            except Exception:
                pass
            try:
                if hasattr(obj, "dict") and callable(obj.dict):
                    return obj.dict()
            except Exception:
                pass
            return obj

        return {"uri": uri, "app_url": None, "raw": _to_primitive(outputs)}
