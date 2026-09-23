import json
from unittest.mock import MagicMock, patch

from src.common.collection import store_dummy_data


@patch("src.common.collection.get_blob_service_client")
def test_store_dummy_data_uploads_json(mock_get_blob_service_client: MagicMock) -> None:
    """The collector uploads a JSON document without contacting Azure."""
    blob_service = mock_get_blob_service_client.return_value
    container_client = blob_service.get_container_client.return_value
    blob_client = container_client.get_blob_client.return_value
    blob_client.url = "https://example.blob.core.windows.net/dummy-data/dummy/test.json"

    blob_url = store_dummy_data()

    blob_service.get_container_client.assert_called_once_with("dummy-data")
    container_client.create_container.assert_not_called()

    blob_name = container_client.get_blob_client.call_args.args[0]
    assert blob_name.startswith("dummy/")
    assert blob_name.endswith(".json")

    uploaded_payload = blob_client.upload_blob.call_args.args[0]
    uploaded_data = json.loads(uploaded_payload)
    assert uploaded_data["source"] == "dummy-function"
    assert uploaded_data["message"] == "Hello from Python"
    assert uploaded_data["collected_at_utc"]
    assert blob_client.upload_blob.call_args.kwargs["overwrite"] is False
    assert blob_client.upload_blob.call_args.kwargs["content_settings"].content_type == "application/json"
    assert blob_url == blob_client.url


@patch("src.common.collection.get_blob_service_client")
@patch("src.common.collection.Path")
def test_collector_includes_packaged_deployment_identity(mock_path, mock_client):
    manifest = mock_path.return_value.resolve.return_value.parents.__getitem__.return_value.__truediv__.return_value
    manifest.exists.return_value = True
    manifest.read_text.return_value = json.dumps({"build_id": "123", "commit": "abc123"})

    store_dummy_data()

    blob = mock_client.return_value.get_container_client.return_value.get_blob_client.return_value
    payload = json.loads(blob.upload_blob.call_args.args[0])
    assert payload["deployment"] == {"build_id": "123", "commit": "abc123"}


@patch("src.common.collection.get_blob_service_client")
def test_same_instant_collections_have_distinct_names(mock_client):
    with patch("src.common.collection.datetime") as clock:
        from datetime import datetime, timezone
        clock.now.return_value = datetime(2026, 9, 10, tzinfo=timezone.utc)
        store_dummy_data()
        store_dummy_data()
    calls = mock_client.return_value.get_container_client.return_value.get_blob_client.call_args_list
    assert calls[0].args[0] != calls[1].args[0]
    assert calls[0].args[0].startswith("dummy/2026/09/10/")


@patch("src.common.collection.get_blob_service_client")
def test_upload_failure_propagates(mock_client):
    import pytest
    blob = mock_client.return_value.get_container_client.return_value.get_blob_client.return_value
    blob.upload_blob.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="storage unavailable"):
        store_dummy_data()


@patch("src.common.collection.BlobServiceClient")
@patch("src.common.collection.get_credential")
def test_blob_client_reuses_connection_pool(mock_credential, mock_client):
    from src.common.collection import get_blob_service_client
    assert get_blob_service_client() is get_blob_service_client()
    mock_client.assert_called_once()
    mock_credential.assert_called_once()
