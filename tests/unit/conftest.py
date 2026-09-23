import pytest

from src.common.collection import get_blob_service_client
from src.services.credential_provider import get_credential


@pytest.fixture(autouse=True)
def collector_environment(monkeypatch):
    monkeypatch.setenv("STORAGE_ACCOUNT_NAME", "teststorage")
    monkeypatch.setenv("CONTAINER_NAME", "dummy-data")
    monkeypatch.delenv("WEBSITE_HOSTNAME", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("IS_FLEX_CONSUMPTION", raising=False)
    get_blob_service_client.cache_clear()
    get_credential.cache_clear()
    yield
    get_blob_service_client.cache_clear()
    get_credential.cache_clear()
