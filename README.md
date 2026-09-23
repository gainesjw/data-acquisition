# Azure Functions data acquisition

A Python collector with managed identity, tested storage writes, and verified Azure Functions releases.

This portfolio copy demonstrates architecture and implementation using sanitized
configuration. Infrastructure names and Fabric identities are illustrative.
Source Git history, credentials, local settings and data extracts are not included.
Azure Pipelines YAML is provided as a reference; it needs your own Azure DevOps
project, repository resources, targets and service connections to run.

## Portfolio projects

- [data-acquisition](https://github.com/gainesjw/data-acquisition): A Python collector with managed identity, tested storage writes, and verified Azure Functions releases.
- [platform-dev](https://github.com/gainesjw/platform-dev): Reusable Azure Pipelines templates and Python tooling for immutable releases, dependency validation, and selective Fabric deployment.
- [analytics-dev](https://github.com/gainesjw/analytics-dev): A source-controlled Power BI semantic model and report with environment-aware lakehouse bindings.
- [data-engineering-dev](https://github.com/gainesjw/data-engineering-dev): PySpark notebooks that ingest public California healthcare workforce datasets into a Fabric lakehouse.
- [policy-engine-dev](https://github.com/gainesjw/policy-engine-dev): An ASP.NET Core API returning complete artifact manifests and per-item governance findings for pipeline enforcement.

## Implementation guide

# Data acquisition

An Azure Functions Python app for collecting external data into Azure Blob
Storage for use in Microsoft Fabric. The current timer-triggered collector
writes a sample JSON record every four hours.

## Getting started

Use Python 3.14. Clone `platform-dev` beside this repository at the revision used
by the pipeline's platform resource; deployment-validation tests import its helpers.

```bash
cd data-acquisition
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp local.settings.example.json local.settings.json
PYTHONPATH="../platform-dev/python" .venv/bin/python -m pytest
```

The default tests mock Azure and need no credentials. To run the Functions host
or upload data, follow [local development and testing](docs/local-development.md)
for authentication, storage settings, Azurite and explicit integration tests.

## Entry points

| Entry point | Purpose |
| --- | --- |
| [function_app.py](function_app.py) | Timer-triggered Function App |
| [src/](src/) | Collector code, configuration and credentials |
| [tests/unit/](tests/unit/) | Mocked application and deployment tests |
| [tests/integration/](tests/integration/) | Explicit tests against Azure storage |
| [.azure-pipelines/ci.yml](.azure-pipelines/ci.yml) | `data-acquisition-ci`: test, stamp and publish the Linux ZIP |
| [.azure-pipelines/cd.yml](.azure-pipelines/cd.yml) | `data-acquisition-cd`: deploy the successful main CI artifact and verify output |

The pipelines consume shared templates from `platform-dev`. Publish platform
changes before consumer changes. Successful main CI runs trigger production CD
once it is registered and enabled; feature-branch CI runs only test and package.
Pipeline registration and migration steps are in the [deployment guide](docs/deployment.md).

## Documentation

- [Local development and testing](docs/local-development.md): authentication,
  configuration, running the host or collector, and unit/integration tests.
- [Build and deployment](docs/deployment.md): CI/CD registration, permissions,
  shared templates, artifact identity and deployment verification.
- [Operations and maintenance](docs/operations.md): retries, monitoring, recovery,
  dependency updates and changing the production storage destination.
