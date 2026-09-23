import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from azure.storage.blob import BlobServiceClient, ContentSettings

from src.services.credential_provider import get_credential
from src.config import get_settings


@lru_cache(maxsize=1)
def get_blob_service_client() -> BlobServiceClient:
    """Reuse a connection pool and credential for the worker's lifetime."""
    account_name = get_settings().account_name
    credential = get_credential()
    return BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=credential,
        connection_timeout=10,
        read_timeout=30,
        retry_total=2,
    )


def store_dummy_data() -> str:
    """Store a small JSON record in Azure Blob Storage and return its URL."""
    container_name = get_settings().container_name
    collected_at = datetime.now(timezone.utc)
    blob_name = f"dummy/{collected_at:%Y/%m/%d}/{uuid4().hex}.json"

    data = {
        "source": "dummy-function",
        "message": "Hello from Python",
        "collected_at_utc": collected_at.isoformat(),
    }

    # Packaged with the code so validation cannot mistake an older deployment
    # for the current build. Local runs do not have a deployment manifest.
    manifest = Path(__file__).resolve().parents[1] / "_deployment.json"
    if manifest.exists():
        data["deployment"] = json.loads(manifest.read_text())

    blob_service = get_blob_service_client()
    container_client = blob_service.get_container_client(container_name)

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        json.dumps(data), overwrite=False,
        content_settings=ContentSettings(content_type="application/json"),
    )

    return blob_client.url


if __name__ == "__main__":
    print(store_dummy_data())
