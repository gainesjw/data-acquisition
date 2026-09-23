from unittest.mock import MagicMock, patch

from src.services.credential_provider import get_credential


@patch("src.services.credential_provider.DefaultAzureCredential")
def test_get_credential_skips_managed_identity_locally(
    mock_default_credential: MagicMock, monkeypatch
) -> None:
    """Local execution avoids probing the unavailable managed-identity endpoint."""
    monkeypatch.delenv("WEBSITE_HOSTNAME", raising=False)

    get_credential()

    mock_default_credential.assert_called_once_with(
        exclude_managed_identity_credential=True
    )


@patch("src.services.credential_provider.ManagedIdentityCredential")
def test_get_credential_uses_only_managed_identity_in_azure(mock_identity, monkeypatch):
    monkeypatch.setenv("WEBSITE_HOSTNAME", "example.azurewebsites.net")
    credential = get_credential()
    assert get_credential() is credential
    mock_identity.assert_called_once_with(client_id=None)


@patch("src.services.credential_provider.ManagedIdentityCredential")
def test_user_assigned_identity(mock_identity, monkeypatch):
    monkeypatch.setenv("WEBSITE_HOSTNAME", "example.azurewebsites.net")
    monkeypatch.setenv("AZURE_CLIENT_ID", "chosen-identity")
    get_credential()
    mock_identity.assert_called_once_with(client_id="chosen-identity")
