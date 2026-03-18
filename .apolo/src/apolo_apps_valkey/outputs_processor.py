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
        # Extract service name and port
        service_name = (
            helm_values.get("fullnameOverride") or f"n8n-{app_instance_id[:16]}-valkey"
        )
        port = helm_values.get("service", {}).get("port", 6379)
        labels = {
            "application": "valkey",
            INSTANCE_LABEL: app_instance_id,
            "app.kubernetes.io/name": service_name,
        }
        (
            internal_web_app_url,
            external_web_app_url,
        ) = await get_internal_external_web_urls(labels)
        # Extract authentication info if enabled
        auth = helm_values.get("auth", {})
        user = None
        password = None
        if auth.get("enabled"):
            acl_users = auth.get("aclUsers", {})
            default_user = acl_users.get("default", {})
            user = "default"
            password = default_user.get("password")
        # Compose URI
        host = f"{service_name}"
        uri = "redis://"
        if user and password:
            uri += f"{user}:{password}@"
        elif user:
            uri += f"{user}@"
        uri += f"{host}:{port}/0"
        # Return a ValkeyAppOutputs model so the base class can call
        # model_dump() on it. Populate both `uri` and `app_url` fields.
        return ValkeyAppOutputs(
            uri=uri,
            app_url=ServiceAPI[WebApp](
                internal_url=internal_web_app_url, external_url=external_web_app_url
            ),
        )
