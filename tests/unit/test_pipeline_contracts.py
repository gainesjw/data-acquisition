"""Protect the CI-to-CD artifact identity and collector hook wiring."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINES = ROOT / ".azure-pipelines"


def read(name):
    return yaml.safe_load((PIPELINES / name).read_text())


def test_ci_builds_without_deploying_and_keeps_manifest_hook():
    ci = read("ci.yml")
    assert ci["extends"]["template"] == "/templates/azure-functions/python/ci/stages.yml@platform"
    params = ci["extends"]["parameters"]
    assert not params.keys() & {"deploy", "azureServiceConnection", "functionAppName", "beforeDeploySteps", "afterDeploySteps"}
    assert params["packageValidationSteps"] == [{"template": "/.azure-pipelines/templates/package-validation.yml@self"}]
    assert ci["variables"] == [{"template": "variables/runtime.yml"}]
    assert "BUILD_BUILDID" in read("templates/package-validation.yml")["steps"][0]["bash"]
    assert "BUILD_SOURCEVERSION" in read("templates/package-validation.yml")["steps"][0]["bash"]


def test_cd_waits_for_complete_main_ci_and_uses_same_platform_ref():
    ci, cd = read("ci.yml"), read("cd.yml")
    assert cd["trigger"] == "none"
    source = cd["resources"]["pipelines"][0]
    assert source["trigger"] == {"branches": {"include": ["refs/heads/main"]}}
    assert source["branch"] == "refs/heads/main"
    assert ci["resources"]["repositories"] == cd["resources"]["repositories"]
    assert cd["extends"]["template"] == "/templates/azure-functions/python/cd/stages.yml@platform"
    params = cd["extends"]["parameters"]
    assert params["artifactPipeline"] == source["pipeline"]
    assert params["dependsOn"] == []
    assert params["deploy"] is True
    assert params["beforeDeploySteps"] == [{"template": "/.azure-pipelines/templates/before-deploy.yml@self"}]
    assert params["afterDeploySteps"] == [{"template": "/.azure-pipelines/templates/after-deploy.yml@self"}]
    for key in ("usePlatformPython", "appCheckoutPath", "platformCheckoutPath", "pythonVersion"):
        assert params[key] == ci["extends"]["parameters"][key]


def test_cd_verifies_ci_build_identity_instead_of_cd_run_identity():
    env = read("templates/after-deploy.yml")["steps"][0]["env"]
    assert env["EXPECTED_BUILD_ID"] == "$(artifactBuildId)"
    assert env["EXPECTED_COMMIT"] == "$(artifactSourceVersion)"


def test_production_and_ci_share_runtime_settings():
    production = read("environments/production.yml")["variables"]
    assert production[0] == {"template": "../variables/runtime.yml"}
    assert not any(p.get("name") in {"pythonVersion", "isFlexConsumption"} for p in production)
    assert set(read("variables/runtime.yml")["variables"]) == {"pythonVersion", "isFlexConsumption"}
