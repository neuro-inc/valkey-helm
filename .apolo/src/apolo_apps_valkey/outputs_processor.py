import typing as t

from apolo_app_types import ServiceAPI
from apolo_app_types.outputs.base import BaseAppOutputsProcessor
from apolo_app_types.outputs.common import (
    INSTANCE_LABEL,
    get_internal_external_web_urls,
)
from apolo_app_types.protocols.common.networking import WebApp

from .app_types import ValkeyAppOutputs


class ValkeyAppOutputProcessor(BaseAppOutputsProcessor[ValkeyAppOutputs]):
    async def _generate_outputs(
        self,
        helm_values: dict[str, t.Any],
        app_instance_id: str,
    ) -> ValkeyAppOutputs:
        # Use the same fullnameOverride as in the Helm values for service discovery
        valkey_service_name = (
            helm_values.get("fullnameOverride") or f"n8n-{app_instance_id[:16]}-valkey"
        )
        labels = {
            "application": "valkey",
            INSTANCE_LABEL: app_instance_id,
            "app.kubernetes.io/name": valkey_service_name,
        }
        (
            internal_web_app_url,
            external_web_app_url,
        ) = await get_internal_external_web_urls(labels)

        return ValkeyAppOutputs(
            app_url=ServiceAPI[WebApp](
                internal_url=internal_web_app_url,
                external_url=external_web_app_url,
            ),
        )
