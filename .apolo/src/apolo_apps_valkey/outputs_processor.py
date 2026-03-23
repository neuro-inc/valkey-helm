import logging
import typing as t
from typing import cast

from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.protocols.common import ApoloSecret
from apolo_apps_valkey.app_types import ValkeyAppOutputs
from apolo_apps_valkey.resp_api import RESPApi


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

    # Construct the AppOutputs using the correct field names defined in
    # `apolo_apps_valkey.app_types.ValkeyAppOutputs`.
    # We map our RESPApi instances to the output fields expected by the
    # application-level schema. Note: `ApoloSecret` is a typing-only
    # construct — we pass a plain dict and use `typing.cast` so mypy can
    # treat it as the proper TypedDict at type-check time.
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
        """Public API used by callers/tests.

        This method ensures a dictionary is always returned (the unit test
        expects a dict). It delegates to the internal `_generate_outputs`
        implementation then normalizes the result into a simple dict with
        a few commonly used keys:

        - "uri": a single connection URI (internal preferred, then external)
        - "app_url": left as None when no HTTP-like URL is applicable
        - "raw": the original outputs object for callers that need full
          access (kept as-is to avoid forcing a particular serialization
          strategy here)
        """
        outputs = await self._generate_outputs(helm_values, app_instance_id)

        # Prefer internal connection when building URI, fall back to external
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

        return {"uri": uri, "app_url": None, "raw": outputs}
