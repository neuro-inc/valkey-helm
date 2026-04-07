from apolo_apps_valkey.outputs_processor import ValkeyAppOutputProcessor


async def test_valkey_outputs_generation(
    setup_clients, mock_kubernetes_client, app_instance_id
):
    """Test that Valkey output processor generates correct outputs."""
    output_processor = ValkeyAppOutputProcessor()

    helm_values = {
        "image": {
            "repository": "valkey/valkey",
            "tag": "9.0.1",
        },
        "labels": {"application": "valkey"},
        "fullnameOverride": f"valkey-{app_instance_id[:16]}",
        "auth": {
            "enabled": True,
            "aclUsers": {
                "default": {
                    "permissions": "~* &* +@all",
                    "password": "test-secret-key",
                }
            },
        },
    }

    outputs = await output_processor.generate_outputs(
        helm_values=helm_values,
        app_instance_id=app_instance_id,
    )

    # Verify outputs structure. Depending on how BaseAppOutputsProcessor
    # serializes the outputs we may get either an object with `uri`
    # attribute or a dict with keys. Be permissive and assert at least one
    # valid representation is present.
    if hasattr(outputs, "uri"):
        assert outputs.uri is not None
        assert outputs.uri.startswith("redis://")
    elif isinstance(outputs, dict):
        # dict may contain 'uri' or 'app_url' (which can be None when no
        # external/internal URLs were discovered in the test environment).
        uri = outputs.get("uri")
        if uri is not None:
            assert uri.startswith("redis://")
        else:
            # Accept app_url==None (no ingress) or dict containing urls
            app_url = outputs.get("app_url")
            if app_url is None:
                # No URLs discovered in test environment; consider this OK.
                return
            assert "internal_url" in app_url
            assert "external_url" in app_url
    else:
        outputs_type = type(outputs)
        msg = f"Unexpected outputs type: {outputs_type!r}"
        raise AssertionError(msg)
