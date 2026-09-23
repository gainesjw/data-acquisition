"""Validate the existing Linux app, then prove the deployed build can write a blob.

Run inside AzureCLI@2; its identity reads storage, while the deployed app writes it.
No collector code is executed by this script.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient

from platform_azure_functions import deployment as functions
from platform_azure_functions.deployment import require, required_env

FUNCTION_NAME = "run_dummy_collector"
SCHEDULE = "0 0 */4 * * *"


def preflight(*, validate_destination=True):
    storage_account = required_env("STORAGE_ACCOUNT_NAME")
    settings = functions.preflight(require_managed_identity=True, require_host_storage=True)
    if validate_destination:
        require(settings.get("STORAGE_ACCOUNT_NAME") == storage_account,
                "STORAGE_ACCOUNT_NAME does not match the pipeline target")
        require(settings.get("CONTAINER_NAME") == required_env("CONTAINER_NAME"),
                "CONTAINER_NAME does not match the pipeline target")
    require(settings.get(f"AzureWebJobs.{FUNCTION_NAME}.Disabled", "").lower() not in ("true", "1"),
            "The collector timer is disabled")
    return settings


def configure():
    """Validate the target before updating only the two collector app settings."""
    required_env("FUNCTION_APP_NAME")
    required_env("RESOURCE_GROUP_NAME")
    destination = {
        "STORAGE_ACCOUNT_NAME": required_env("STORAGE_ACCOUNT_NAME"),
        "CONTAINER_NAME": required_env("CONTAINER_NAME"),
    }
    # Inspect runtime/identity/host settings and storage access before any mutation.
    settings = preflight(validate_destination=False)
    check_storage_access()
    if all(settings.get(name) == value for name, value in destination.items()):
        print("Collector destination already configured; no app settings update needed")
        return
    functions.az("config", "appsettings", "set", "--settings",
       *(f"{name}={value}" for name, value in destination.items()))
    print("Collector destination configured; host storage settings preserved")


def matches_build(data, started):
    """Reject old, unrelated and malformed collector output."""
    try:
        return (
            data["source"] == "dummy-function"
            and data["deployment"]["build_id"] == os.environ["EXPECTED_BUILD_ID"]
            and data["deployment"]["commit"] == os.environ["EXPECTED_COMMIT"]
            and datetime.fromisoformat(data["collected_at_utc"]) >= started
        )
    except (KeyError, TypeError, ValueError):
        return False


def storage_client():
    return BlobServiceClient(
        account_url=f"https://{required_env('STORAGE_ACCOUNT_NAME')}.blob.core.windows.net",
        credential=AzureCliCredential(), connection_timeout=10, read_timeout=30,
        retry_total=2,
    ).get_container_client(required_env("CONTAINER_NAME"))


def storage_error(exc):
    """Report service error metadata without dumping response bodies or tokens."""
    code = str(getattr(exc, "error_code", None) or "Unknown")
    if not re.fullmatch(r"[A-Za-z0-9_]+", code):
        code = "Unknown"
    message = f"Blob storage read failed: HTTP {exc.status_code}, Azure error {code}. "
    if exc.status_code == 403:
        message += (
            "Check Storage Blob Data Reader for the Azure DevOps service connection identity "
            "on the target storage account/container (Contributor or Owner alone does not grant blob data access). "
            "Also check storage network restrictions and allow time for new role assignments to propagate."
        )
    else:
        message += "Check storage availability, authentication and network access."
    return message


def check_storage_access():
    """Fail before deployment if the pipeline identity cannot list blob data."""
    try:
        next(iter(storage_client().list_blobs(results_per_page=1)), None)
    except ResourceNotFoundError:
        raise RuntimeError("Provision CONTAINER_NAME before deployment; the collector does not create containers") from None
    except HttpResponseError as exc:
        raise RuntimeError(storage_error(exc)) from None
    print("Preflight passed: pipeline identity can list blob data", flush=True)


def recent_blobs(container, started):
    """Scan only UTC date partitions covered by this verification (including midnight)."""
    day = started.date()
    today = datetime.now(timezone.utc).date()
    while day <= today:
        yield from container.list_blobs(name_starts_with=f"dummy/{day:%Y/%m/%d}/")
        day += timedelta(days=1)


def verify():
    for name in ("STORAGE_ACCOUNT_NAME", "CONTAINER_NAME", "EXPECTED_BUILD_ID", "EXPECTED_COMMIT"):
        required_env(name)
    hostname, key = functions.wait_for_function(
        FUNCTION_NAME, binding_type="timerTrigger", schedule=SCHEDULE,
    )
    container = storage_client()
    started = datetime.now(timezone.utc)
    # A 202 only accepts the invocation; storage verification proves execution.
    status, _ = functions.host_request(hostname, key, f"/admin/functions/{FUNCTION_NAME}", {})
    require(status == 202, f"Expected invocation acceptance (202), received {status}")
    print("Azure accepted the timer invocation; checking for fresh output from this build", flush=True)

    def output_exists():
        try:
            for blob in recent_blobs(container, started):
                if blob.last_modified < started.replace(microsecond=0):
                    continue
                content = container.download_blob(blob.name).readall()
                try:
                    data = json.loads(content)
                except (ValueError, UnicodeDecodeError):
                    continue
                if matches_build(data, started):
                    print(f"Verified blob: {blob.name}", flush=True)
                    return True
        except ResourceNotFoundError:
            # A blob can disappear between listing and download.
            return False
        except HttpResponseError as exc:
            raise RuntimeError(storage_error(exc)) from None
        return False

    functions.wait_until(output_exists, "fresh collector blob matches the deployed build and commit")
    print(f"Deployment validated: build {os.environ['EXPECTED_BUILD_ID']}")


if __name__ == "__main__":
    try:
        {"configure": configure, "preflight": preflight, "storage-check": check_storage_access, "verify": verify}[sys.argv[1]]()
    except Exception as exc:
        # Avoid dumping HTTP headers, credentials or downloaded blob contents.
        print(f"Validation failed ({type(exc).__name__}). "
              + (str(exc) if isinstance(exc, RuntimeError) else
                 "Check app logs, service connection permissions and network access."), file=sys.stderr)
        sys.exit(1)
