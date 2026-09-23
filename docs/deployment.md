# Build and deployment

[Repository README](../README.md)

CI and CD run as separate Azure DevOps pipelines:

| Pipeline | YAML entry point | Responsibility |
| --- | --- | --- |
| `data-acquisition-ci` | [`.azure-pipelines/ci.yml`](../.azure-pipelines/ci.yml) | Run unit tests, validate and stamp the package, publish the Linux ZIP |
| `data-acquisition-cd` | [`.azure-pipelines/cd.yml`](../.azure-pipelines/cd.yml) | On successful main CI completion, verify the selected CI run, deploy its ZIP and verify collector output |

Rename the existing `data-acquisition-ci-cd` pipeline to `data-acquisition-ci`,
keeping its pipeline ID and updating its YAML path to `.azure-pipelines/ci.yml`.
Its build history and existing policy references stay attached to that definition.
Register a new `data-acquisition-cd`
definition pointing to `cd.yml`; the YAML pipeline resource references the renamed
CI definition by its exact display name. These registration changes happen in
Azure DevOps; editing YAML alone does not create or rename pipeline definitions.

The components come from `platform-dev/templates/azure-functions/python/ci/stages.yml`
and `platform-dev/templates/azure-functions/python/cd/stages.yml`, respectively,
through the `platform` repository resource. Both currently follow `refs/heads/main`;
pin both to the same existing platform release tag for controlled upgrades.

The production service connection, Function App and environment are retained.
The target uses **Flex Consumption (FC1) and Python 3.14**. The runtime values live
in [`.azure-pipelines/variables/runtime.yml`](../.azure-pipelines/variables/runtime.yml),
shared by CI and production CD. CI does not load production target settings or
reference a deployment service connection. Infrastructure provisioning remains
outside these pipelines.

This repo retains its triggers and production values, plus three collector-specific
step templates under `.azure-pipelines/templates/`: `package-validation.yml`,
`before-deploy.yml`, and `after-deploy.yml`. These stamp the deployment manifest,
validate the named collector, configure its storage destination and verify its
output. They reference `.azure-pipelines/scripts/validate_deployment.py`, which retains
collector policy and blob checks and imports common runtime/readiness utilities
from `platform-dev/python/platform_azure_functions/deployment.py`.
The `@self` suffix resolves these hooks from this app repo.

Together, the shared stages and collector hooks:

1. Install locked dependencies, check their compatibility, run mocked unit tests,
   and publish JUnit results and coverage for application and deployment code.
2. Install Linux dependencies into `.python_packages/lib/site-packages`, copy
   application files, embed the build ID and commit in `src/_deployment.json`,
   and verify the packaged Function App imports and indexes the collector.
3. On successful `main` CI completion, CD selects that exact run's artifact. It
   rejects failed, partially successful, PR or non-main CI runs and checks that
   the CI repository and commit match the CD checkout. It then checks runtime, identity, host configuration and
   destination storage access. Apply the two collector destination settings when
   needed, validate them, then deploy the published ZIP to `production`.
4. Poll for a running Functions host and the named timer with its expected
   four-hour schedule. Invoke the deployed timer through its authenticated
   admin endpoint, then poll storage for fresh JSON matching the upstream CI build ID
   and commit. Each polling phase allows five minutes; failures fail deployment.

CD never rebuilds the application ZIP. Its `appCI` pipeline resource downloads
the artifact to `$(Pipeline.Workspace)/appCI/function-package/function-app.zip`,
exposed to hooks as `$(functionPackagePath)`. The verification hook uses
`$(artifactBuildId)` and `$(artifactSourceVersion)` from CI, not the separate CD
run's build ID. The manifest stamped by CI remains unchanged during release.
Same-repository completion triggers keep the checked-out hooks at the CI commit.
Manual CD runs must select a CI run matching the CD checkout; an older artifact
with a newer main checkout is rejected. The completion trigger waits for all CI
stages, so future CI integration stages are included in the release gate.

The runtime adds a `deployment` object to collected JSON when a packaged
manifest is present. Local runs keep their existing payload. Verification invokes
one real collection and leaves its blob in `dummy-data`. A 202 response or an old
blob is insufficient to pass. A scheduled execution of this same build during
verification can also satisfy the output check; it proves the deployed code runs
and writes successfully, but does not correlate a specific invocation or prove
future scheduled executions.

## Azure DevOps and Azure setup

- For this migration, merge/push the `platform-dev` template to its `main` branch
  **before** merging/pushing the consuming pipeline change here. Azure DevOps
  reads remote Git content, not these local sibling folders.
- Grant the pipeline's Build Service identity Read access to `platform-dev` and
  authorize the repository resource when Azure DevOps requests it. Both repos
  are in `example-fabric-project`, so the resource uses `type: git` and
  `name: platform-dev` without an additional repository service connection.
  `usePlatformPython: true` checks out the same platform resource revision in both
  Build and Deploy: the app lives at `$(Pipeline.Workspace)/s/data-acquisition` and platform at
  `$(Pipeline.Workspace)/s/platform-dev`. The app checkout sets `workspaceRepo: true`
  so relative commands run from the app root. Test and verification steps receive the platform
  `python` directory through `PYTHONPATH: $(platformPythonPath)`. Shared tooling stays out of the app ZIP.
- For a build-only first run, push the consumer change to a feature branch and
  run the existing CI definition. CI no longer has a `deploy` parameter and never
  deploys directly. Verify CI before enabling the new CD pipeline. Once CD is
  registered, successful main CI runs automatically start production CD.
  For controlled template upgrades, create a release tag in `platform-dev` and
  change both repository resource refs to that same existing `refs/tags/...` tag.

- Rename `data-acquisition-ci-cd` to `data-acquisition-ci` and change its YAML
  path from `.azure-pipelines/azure-pipelines.yml` to `.azure-pipelines/ci.yml`.
  Update the existing definition rather than creating a replacement CI definition.
  Create `data-acquisition-cd`
  from `.azure-pipelines/cd.yml` after the updated CI has passed. Set its default
  branch to `refs/heads/main` and authorize the `appCI` resource. The CD Build
  Service identity needs permission to view CI builds and download artifacts;
  verification uses Azure DevOps' `System.AccessToken`, without a PAT. Both
  pipelines must remain in this project and repository.
- For the CD pipeline, authorize `REPLACE_WITH_AZURE_SERVICE_CONNECTION` and the `production`
  environment. Configure an **exclusive lock** check on that environment to
  serialize deployment and verification across runs (`lockBehavior: sequential`).
- The service connection needs permission to deploy/read the Function App, read
  and update its app settings, and retrieve host keys (`Microsoft.Web/sites/host/listkeys/action`).
  It also needs **Storage Blob Data Reader** on `examplestorageaccount` for validation.
  The verifier holds the master key in memory and never prints it.
- The Function App's managed identity needs **Storage Blob Data Contributor**
  on the target storage account. If using a user-assigned identity, configure
  `AZURE_CLIENT_ID` appropriately. The pipeline's storage identity only reads;
  blob writes execute inside the deployed Function App.
- Configure Python 3.14 under the Flex app's `functionAppConfig.runtime`,
  and working `AzureWebJobsStorage` settings
  (connection string or identity-based configuration with its required roles).
  Flex manages the host version and does not require the legacy
  `FUNCTIONS_WORKER_RUNTIME` or `FUNCTIONS_EXTENSION_VERSION` app settings.
  The pipeline sets `STORAGE_ACCOUNT_NAME` and `CONTAINER_NAME` from
  `.azure-pipelines/environments/production.yml` (currently `examplestorageaccount`
  and `dummy-data`). Provision that container before
  deployment. Preflight fails if it is missing. The collector must not be disabled.
- The build agent must reach the Function App's HTTPS admin endpoint, deployment
  endpoint, and blob storage. Use an agent with suitable network access for
  private endpoints or access restrictions. Admin endpoints must be enabled.
- For **Azure Repos**, use `data-acquisition-ci` as the build-validation branch policy on
  `main`; YAML `pr` triggers apply to supported external repositories such as
  GitHub. PR and non-main builds only test/package and do not access Azure.

For a manual build without deployment, run CI on a feature branch. A successful
main CI run will trigger CD once that pipeline is registered and enabled.
The former `test-azure-pipelines.yml`, `test-functions.yml`, and
`test-key-vault.yml` diagnostic pipelines have been removed. Delete or disable
any Azure DevOps pipeline definitions that still reference those paths.

Deployment verification follows Microsoft's
[manual non-HTTP function invocation procedure](https://learn.microsoft.com/en-us/azure/azure-functions/functions-manually-run-non-http).
A failed post-deployment check marks the deployment failed but does not roll back
the code; inspect Application Insights/Function App logs and redeploy a known-good
version if needed.

See also [operations](operations.md) for recovery and production configuration changes.
