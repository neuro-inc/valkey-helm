import pytest
from apolo_apps_valkey.outputs_processor import ValkeyAppOutputProcessor


@pytest.fixture
def mock_kubernetes_client():
    # Minimal stub, expand as needed
    class Dummy:
        pass

    return Dummy()


async def test_valkey_outputs_generation(
    setup_clients, mock_kubernetes_client, app_instance_id, monkeypatch
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

    # Updated assertions for ValkeyAppOutputs structure (dict-based)
    assert "redis" in outputs, "outputs missing 'redis' key"
    assert "connection" in outputs, "outputs missing 'connection' key"
    connection = outputs["connection"]
    assert connection is not None, "outputs['connection'] is None"
    # connection should have a 'uri' property or enough info to construct it
    # If 'uri' is not present, reconstruct it from fields
    uri = connection.get("uri")
    if uri is None:
        user = connection.get("user", "default")
        password = connection.get("password")
        if isinstance(password, dict):
            password = password.get("key")
        host = connection.get("host")
        port = connection.get("port")
        creds = f"{user}:{password}" if user else f":{password}"
        uri = f"redis://{creds}@{host}:{port}"
    assert isinstance(uri, str), f"uri is not a string: {uri}"
    assert uri.startswith("redis://"), f"Invalid redis uri: {uri}"
    # Optionally, check host, port, user, password
    assert connection["host"].startswith(
        "valkey-"
    ), f"Unexpected host: {connection['host']}"
    assert connection["port"] == 6379, f"Unexpected port: {connection['port']}"
    assert connection["user"] == "default", f"Unexpected user: {connection['user']}"
    password = connection["password"]
    if isinstance(password, dict):
        password = password.get("key")
    assert password == "test-secret-key", f"Unexpected password: {password}"
