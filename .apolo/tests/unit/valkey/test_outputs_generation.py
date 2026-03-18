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
    }

    outputs = await output_processor.generate_outputs(
        helm_values=helm_values,
        app_instance_id=app_instance_id,
    )

    # Verify outputs structure
    assert "app_url" in outputs
    assert "internal_url" in outputs["app_url"]
    assert "external_url" in outputs["app_url"]
