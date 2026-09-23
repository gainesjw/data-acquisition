"""Exercise deployment verification without Azure access."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

spec = importlib.util.spec_from_file_location(
    "validate_deployment",
    Path(__file__).resolve().parents[2] / ".azure-pipelines/scripts/validate_deployment.py",
)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


@pytest.fixture
def expected_build(monkeypatch):
    monkeypatch.setenv("EXPECTED_BUILD_ID", "123")
    monkeypatch.setenv("EXPECTED_COMMIT", "abc123")
    return datetime.now(timezone.utc)


@pytest.mark.parametrize("difference", [None, "old", "build", "commit", "source", "malformed"])
def test_only_fresh_output_from_expected_build_passes(expected_build, difference):
    data = {
        "source": "dummy-function",
        "deployment": {"build_id": "123", "commit": "abc123"},
        "collected_at_utc": expected_build.isoformat(),
    }
    if difference == "old":
        data["collected_at_utc"] = (expected_build - timedelta(seconds=1)).isoformat()
    elif difference in ("build", "commit"):
        data["deployment"]["build_id" if difference == "build" else "commit"] = "other"
    elif difference == "source":
        data["source"] = "other"
    elif difference == "malformed":
        data = {}
    assert validation.matches_build(data, expected_build) is (difference is None)


@pytest.fixture
def preflight_responses(monkeypatch):
    for name, value in {
        "FUNCTION_APP_NAME": "test-app",
        "RESOURCE_GROUP_NAME": "test-group",
        "PYTHON_VERSION": "3.12",
        "STORAGE_ACCOUNT_NAME": "examplestorageaccount",
        "CONTAINER_NAME": "dummy-data",
    }.items():
        monkeypatch.setenv(name, value)
    return [
        {"kind": "functionapp,linux", "state": "Running",
         "identity": {"type": "SystemAssigned"}},
        {"linuxFxVersion": "PYTHON|3.12"},
        [{"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"},
         {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
         {"name": "STORAGE_ACCOUNT_NAME", "value": "examplestorageaccount"},
         {"name": "CONTAINER_NAME", "value": "dummy-data"},
         {"name": "AzureWebJobsStorage", "value": "private-test-value"}],
    ]


def mock_cli(monkeypatch, responses):
    import json
    run = MagicMock(side_effect=[
        MagicMock(returncode=0, stdout=json.dumps(response)) for response in responses
    ])
    monkeypatch.setattr(validation.functions.subprocess, "run", run)
    return run


def test_storage_permission_error_is_actionable_and_redacted(monkeypatch):
    error = validation.HttpResponseError(message="secret response body")
    error.status_code = 403
    error.error_code = "AuthorizationPermissionMismatch"
    client = MagicMock()
    # Listing fails on iteration, as it does in the SDK.
    def denied():
        raise error
        yield
    client.list_blobs.return_value = denied()
    monkeypatch.setattr(validation, "storage_client", lambda: client)
    with pytest.raises(RuntimeError) as caught:
        validation.check_storage_access()
    message = str(caught.value)
    assert "HTTP 403" in message
    assert "AuthorizationPermissionMismatch" in message
    assert "Storage Blob Data Reader" in message
    assert "service connection identity" in message
    assert "secret response body" not in message


def test_storage_access_check_accepts_empty_container(monkeypatch, capsys):
    client = MagicMock()
    client.list_blobs.return_value = iter([])
    monkeypatch.setattr(validation, "storage_client", lambda: client)
    validation.check_storage_access()
    assert "pipeline identity can list blob data" in capsys.readouterr().out


def test_storage_access_check_requires_provisioned_container(monkeypatch):
    client = MagicMock()
    client.list_blobs.side_effect = validation.ResourceNotFoundError()
    monkeypatch.setattr(validation, "storage_client", lambda: client)
    with pytest.raises(RuntimeError, match="Provision CONTAINER_NAME"):
        validation.check_storage_access()


@pytest.mark.parametrize("setting", ["STORAGE_ACCOUNT_NAME", "CONTAINER_NAME"])
def test_preflight_rejects_missing_collector_settings(monkeypatch, preflight_responses, setting):
    preflight_responses[2] = [v for v in preflight_responses[2] if v["name"] != setting]
    mock_cli(monkeypatch, preflight_responses)
    with pytest.raises(RuntimeError, match=setting):
        validation.preflight()


def test_recent_blobs_includes_midnight_rollover(monkeypatch):
    started = datetime(2026, 9, 10, 23, 59, 59, tzinfo=timezone.utc)
    clock = MagicMock()
    clock.now.return_value = started + timedelta(seconds=2)
    monkeypatch.setattr(validation, "datetime", clock)
    container = MagicMock()
    list(validation.recent_blobs(container, started))
    assert [call.kwargs["name_starts_with"] for call in container.list_blobs.call_args_list] == [
        "dummy/2026/09/10/", "dummy/2026/09/11/",
    ]


@pytest.mark.parametrize("wrong_build", [False, True])
def test_full_verification_requires_fresh_deployed_output(monkeypatch, expected_build, wrong_build):
    import json
    for name, value in {"FUNCTION_APP_NAME": "test", "RESOURCE_GROUP_NAME": "test"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(validation.functions, "az", MagicMock(side_effect=[
        {"defaultHostName": "test.azurewebsites.net"},
        {"masterKey": "private-key"},
        [{"name": "test/run_dummy_collector", "config": {"bindings": [
            {"type": "timerTrigger", "schedule": validation.SCHEDULE},
        ]}}],
    ]))
    request = MagicMock(side_effect=[(200, {"state": "Running"}), (202, None)])
    monkeypatch.setattr(validation.functions, "host_request", request)
    container = MagicMock()
    blob = MagicMock(name="blob")
    blob.name = "dummy/2026/09/10/sample.json"
    blob.last_modified = datetime.now(timezone.utc) + timedelta(seconds=1)
    container.list_blobs.return_value = [blob]
    container.download_blob.return_value.readall.return_value = json.dumps({
        "source": "dummy-function",
        "deployment": {"build_id": "wrong" if wrong_build else "123", "commit": "abc123"},
        "collected_at_utc": blob.last_modified.isoformat(),
    }).encode()
    monkeypatch.setattr(validation, "storage_client", lambda: container)
    # Exercise the actual polling code, advancing its deadline without sleeping.
    ticks = iter(range(0, 2000, 301))
    monkeypatch.setattr(validation.functions.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(validation.functions.time, "sleep", MagicMock())
    if wrong_build:
        with pytest.raises(RuntimeError, match="Timed out"):
            validation.verify()
    else:
        validation.verify()
    assert request.call_args.args == (
        "test.azurewebsites.net", "private-key", "/admin/functions/run_dummy_collector", {},
    )


def test_configure_updates_only_collector_settings_after_checks(monkeypatch, preflight_responses, capsys):
    preflight_responses[2] = [item for item in preflight_responses[2]
                              if item["name"] not in ("STORAGE_ACCOUNT_NAME", "CONTAINER_NAME")]
    run = mock_cli(monkeypatch, preflight_responses + [
        [{"name": "AzureWebJobsStorage", "value": "private-response-value"}],
    ])
    events = []
    check = MagicMock(side_effect=lambda: events.append("storage-checked"))
    monkeypatch.setattr(validation, "check_storage_access", check)
    original_run = run.side_effect
    def cli_call(*args, **kwargs):
        if "set" in args[0]:
            assert events == ["storage-checked"]
        return next(original_run)
    run.side_effect = cli_call
    validation.configure()
    command = run.call_args.args[0]
    assert command[:6] == ["az", "functionapp", "config", "appsettings", "set", "--settings"]
    assert command[6:8] == ["STORAGE_ACCOUNT_NAME=examplestorageaccount", "CONTAINER_NAME=dummy-data"]
    assert not any("AzureWebJobsStorage=" in arg for arg in command)
    output = capsys.readouterr().out
    assert "private-response-value" not in output
    assert "private-test-value" not in output


def test_configure_skips_matching_settings(monkeypatch, preflight_responses):
    run = mock_cli(monkeypatch, preflight_responses)
    monkeypatch.setattr(validation, "check_storage_access", MagicMock())
    validation.configure()
    assert run.call_count == 3
    assert all("set" not in call.args[0] for call in run.call_args_list)


def test_configure_does_not_mutate_when_storage_check_fails(monkeypatch, preflight_responses):
    run = mock_cli(monkeypatch, preflight_responses)
    monkeypatch.setattr(validation, "check_storage_access", MagicMock(side_effect=RuntimeError("missing container")))
    with pytest.raises(RuntimeError, match="missing container"):
        validation.configure()
    assert all("set" not in call.args[0] for call in run.call_args_list)


def test_configure_does_not_mutate_wrong_runtime(monkeypatch, preflight_responses):
    preflight_responses[1]["linuxFxVersion"] = "PYTHON|3.11"
    run = mock_cli(monkeypatch, preflight_responses)
    check = MagicMock()
    monkeypatch.setattr(validation, "check_storage_access", check)
    with pytest.raises(RuntimeError, match="Runtime mismatch"):
        validation.configure()
    check.assert_not_called()
    assert all("set" not in call.args[0] for call in run.call_args_list)


def test_configure_requires_destination_before_azure_calls(monkeypatch):
    monkeypatch.setenv("FUNCTION_APP_NAME", "test-app")
    monkeypatch.setenv("RESOURCE_GROUP_NAME", "test-group")
    monkeypatch.delenv("CONTAINER_NAME", raising=False)
    cli = MagicMock()
    monkeypatch.setattr(validation.functions, "az", cli)
    with pytest.raises(RuntimeError, match="CONTAINER_NAME"):
        validation.configure()
    cli.assert_not_called()


@pytest.mark.parametrize("missing", ["identity", "host_storage", "enabled_timer"])
def test_collector_preserves_required_capabilities(monkeypatch, preflight_responses, missing):
    if missing == "identity":
        preflight_responses[0]["identity"] = None
        message = "managed identity"
    elif missing == "host_storage":
        preflight_responses[2] = [v for v in preflight_responses[2] if v["name"] != "AzureWebJobsStorage"]
        message = "AzureWebJobsStorage"
    else:
        preflight_responses[2].append({"name": "AzureWebJobs.run_dummy_collector.Disabled", "value": "true"})
        message = "collector timer is disabled"
    mock_cli(monkeypatch, preflight_responses)
    with pytest.raises(RuntimeError, match=message):
        validation.preflight()
