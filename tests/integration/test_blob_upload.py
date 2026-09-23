import pytest
from src.common.collection import store_dummy_data

@pytest.mark.integration
def test_store_dummy_data():
    """Test that store_dummy_data() successfully uploads a JSON record to Azure Blob Storage."""
    print("Uploading a dummy record to the configured storage account...")
    blob_url = store_dummy_data()
    print(f"Uploaded test blob: {blob_url}")
    assert blob_url.startswith("https://")
    assert blob_url.endswith(".json")
