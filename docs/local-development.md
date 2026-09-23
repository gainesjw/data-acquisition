# Local development and testing

[Repository README](../README.md)

Run the commands below from the repository root after completing the
[local setup](../README.md#getting-started). Clone `platform-dev` beside this repository
for deployment-validation tests.

## Local Azure authentication

The collector uses `DefaultAzureCredential` locally and explicit
`ManagedIdentityCredential` in Azure. For local execution, sign in with
the Azure CLI using the same account that has the `Storage Blob Data Contributor`
role on the target storage account:

```bash
az login
az account set --subscription "<your-subscription-id-or-name>"
func start
```

Set both `STORAGE_ACCOUNT_NAME` and `CONTAINER_NAME` explicitly in
`local.settings.json` for local runs. Production app settings are applied by the
pipeline from `.azure-pipelines/environments/production.yml`. Create the container before running
the collector. Local host storage uses Azurite (`UseDevelopmentStorage=true`);
start Azurite before `func start`. The collector writes to the configured Azure
account using your developer identity.

## Testing

Run the mocked unit tests (the default) without Azure credentials. Deployment
validation imports shared helpers from `platform-dev`; clone it next to this repo
and use the revision selected by the pipeline resource ref:

```bash
PYTHONPATH="../platform-dev/python" .venv/bin/python -m pytest
```

If you are still using the existing virtual environment stored in this project
as `bin/`, substitute `bin/python` for `.venv/bin/python` in the commands.

To upload to the real storage account, first sign in with `az login`, then run
the integration test explicitly against a pre-created test container. Export
`STORAGE_ACCOUNT_NAME` and `CONTAINER_NAME` first; pytest does not load local settings:

```bash
.venv/bin/python -m pytest -m integration -vv -s
```

To run the collector itself, run it as a module from the project root so Python
can resolve the `src` package. Plain Python and pytest do not load
`local.settings.json`; export the two storage settings first:

```bash
export STORAGE_ACCOUNT_NAME="<your-storage-account>"
export CONTAINER_NAME="dummy-data"
.venv/bin/python -m src.common.collection
```

See also [deployment](deployment.md) and [operations](operations.md).
