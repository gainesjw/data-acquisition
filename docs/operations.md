# Operations and maintenance

[Repository README](../README.md)

## Reliability and operations

- Timer failures use [three fixed-delay retries, ten seconds apart](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-error-pages).
  Blob requests also have bounded SDK retries and connection/read timeouts.
  Host restarts can interrupt timer retries; this is not a durable recovery queue.
- Output uses `dummy/YYYY/MM/DD/<uuid>.json` in UTC, with JSON content type and
  overwrite disabled. Each execution is a separate sample. Retries after an
  ambiguous upload can produce duplicate logical records; real source collectors
  must define source/window deduplication before requiring exactly-once results.
- Verification scans only the UTC date partitions spanned by the check, including
  midnight rollover. Old output paths remain untouched.
- Clients and credentials are reused within a worker. Restart the worker after
  changing configuration or identity. The app does not create containers.
- Configure Application Insights and alerts for failed executions and absence of
  successful collection beyond the four-hour interval plus retry allowance.
  Infrastructure, RBAC, alerts and environment locks belong in a version-controlled
  infrastructure repository; this repository does not provision them.
- After exhausted retries, inspect the exception and last successful output, fix
  the cause, and manually invoke the timer to collect a fresh sample. This dummy
  collector cannot reconstruct historical samples. When real collectors are added,
  implement explicit collection windows and a backfill command for missed windows.
- Deployment failure does not roll back automatically. Redeploy a known-good
  artifact and verify it before considering the incident resolved.

## Updating dependencies

`requirements.txt` locks runtime dependencies, including transitive dependencies.
`requirements-dev.txt` adds locked test tools. Both target Python 3.14 on
Linux/macOS. Update the complete dependency graph together in a clean Python 3.14
virtual environment, review the diff, run `python -m pip check` and the unit suite,
and let the Linux pipeline validate the package before deployment. Do not freeze
an unrelated developer environment (which may include platform-specific brokers).

## Changing the production blob destination

Edit `storageAccountName` and `containerName` in
[the production configuration](../.azure-pipelines/environments/production.yml), then
run CI from `main`; its successful completion triggers the configured CD pipeline.
No separate test environment is
configured. Build-only and PR runs never update Azure app settings.

Before switching accounts, create the destination container, grant the Function
App identity Storage Blob Data Contributor and the service connection Storage
Blob Data Reader on the new destination, and allow network access from both.
Resource creation and role assignments remain outside this pipeline.

The configuration step checks the runtime, identity, host configuration and the
pipeline's storage read access before changing anything. It only updates
`STORAGE_ACCOUNT_NAME` and `CONTAINER_NAME`; `AzureWebJobsStorage` stays unchanged.
Matching settings skip the update to avoid an unnecessary restart. App setting
changes can restart the app and redirect scheduled executions immediately, even
if a later deployment step fails. To restore the previous destination, restore
the two values in the production configuration and rerun the pipeline.

See also [deployment](deployment.md) for pipeline setup and permissions, and
[local testing](local-development.md#testing) for test commands.
