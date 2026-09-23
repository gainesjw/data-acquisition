import os
from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


@lru_cache(maxsize=1)
def get_credential() -> TokenCredential:
    """Return the credential suitable for the current execution environment.

    Locally, DefaultAzureCredential uses the developer's Azure CLI sign-in (or
    other configured developer credentials). In Azure, it uses the Function
    App's managed identity.
    """
    running_in_azure = bool(os.getenv("WEBSITE_HOSTNAME"))

    if running_in_azure:
        return ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID") or None)

    return DefaultAzureCredential(
        # A local machine has no managed-identity endpoint. Skipping it avoids
        # an unnecessary metadata-service request during local runs.
        exclude_managed_identity_credential=True,
    )
