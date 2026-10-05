"""python3 test_posture.py — offline checks of posture.py against a canned workspace (no network)."""
import argparse
import json
import tempfile
from pathlib import Path

import posture

TIER = "Error: These keys are not available for your pricing tier: [\"enableIpAccessLists\"]"
WORKSPACE = {
    "/api/2.0/preview/scim/v2/Me": {"displayName": "eurostream-ci", "groups": [{"display": "admins"}]},
    "/api/2.0/settings/types/restrict_workspace_admins/names/default": {"restrict_workspace_admins": {"status": "ALLOW_ALL"}},
    "/api/2.0/preview/workspace-conf?keys=maxTokenLifetimeDays": {"maxTokenLifetimeDays": "730"},
    "/api/2.0/preview/workspace-conf?keys=enableResultsDownloading": {"enableResultsDownloading": None},
    "/api/2.0/serving-endpoints": {"endpoints": [{"name": "databricks-llama", "endpoint_type": "FOUNDATION_MODEL_API"}]},
    "/api/2.2/jobs/list?limit=100": {"jobs": [{"job_id": 1, "run_as_user_name": "a@b.com", "creator_user_name": "a@b.com",
                                               "settings": {"name": "nightly"}}]},
    "/api/2.0/permissions/jobs/1": {"access_control_list": [
        {"group_name": "users", "all_permissions": [{"permission_level": "CAN_MANAGE", "inherited": False}]}]},
}


def fetch(path):
    if "enableIpAccessLists" in path:
        return False, TIER
    return (True, WORKSPACE[path]) if path in WORKSPACE else (False, "Error: PERMISSION_DENIED")


def args(out, **kw):
    base = dict(out=str(out), workspace=True, profile=None, cli="databricks", sat_results=None, iac=None,
                cloud="aws", allowed_regions=None, from_posture=None, read_as="service-principal")
    return argparse.Namespace(**{**base, **kw})


def test_live_rules_score_and_records():
    with tempfile.TemporaryDirectory() as d:
        results, score = posture.run(args(d), fetch=fetch)
        assert results["GOV-35"]["status"] == "fail"                      # ALLOW_ALL
        assert results["IA-5"]["status"] == "pass"                        # a limit exists (SAT's rule)
        assert results["VX-IA-1"]["status"] == "fail"                     # but 730 > 90 (ours)
        assert results["DP-5"]["status"] == "fail"                        # unset → platform default true
        assert results["NS-11"]["reason"] == "not available on this pricing tier"
        assert results["NS-7"]["status"] == "pass"                        # hosted foundation models do not count
        assert results["GOV-42"]["status"] == "fail" and results["GOV-45"]["status"] == "fail"
        assert results["NS-3"]["status"] == "not_assessed"                # account API never guessed
        assert results["GOV-2"]["reason"].startswith("permission")
        findings = [json.loads(x) for x in (Path(d) / "findings.jsonl").read_text().splitlines()]
        ids = {f["id"] for f in findings}
        assert "FND-SEC-GOV-35" in ids and all(f["status"] == "extracted" for f in findings)
        assert all(f["evidence"][0]["locator"].startswith("GET ") and f["evidence"][1]["kind"] == "external" for f in findings)
        rdy = json.loads((Path(d) / "readiness.jsonl").read_text())
        assert rdy["basis"] == "workspace" and rdy["score"] == score is None   # canned workspace covers <50%
        assert "not scored" in rdy["needs"]
        assert "pricing tier" in rdy["needs"]
        assert json.loads((Path(d) / "manifest.json").read_text())["external_access"]


def test_score_caps():
    hi = [c for c, v in posture.CHECKS.items() if v["severity"] == "high" and v["scope"] == "workspace"]
    passing = {c: posture.result("pass") for c in posture.CHECKS if posture.CHECKS[c]["scope"] == "workspace"}
    assert posture.score(passing)[0] == 5
    assert posture.score({**passing, hi[0]: posture.result("fail")})[0] == 3
    assert posture.score({**passing, **{c: posture.result("fail") for c in hi[:3]}})[0] == 2
    assert posture.score({c: posture.result("fail", source="iac") for c in hi})[0] is None   # code alone never scores


def test_sat_rows_and_iac():
    sat = posture.from_sat([{"check_id": "GOV-3", "score": 1, "run_id": 7, "additional_details": {"m": "no audit delivery"}},
                            {"check_id": "NS-3", "score": 0, "run_id": 7}])
    assert sat["GOV-3"]["status"] == "fail" and sat["NS-3"]["status"] == "pass" and "run_id=7" in sat["GOV-3"]["locator"]
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "50_grants.sql").write_text("GRANT SELECT ON SCHEMA gold TO `analysts`;\n"
                                               "GRANT ALL PRIVILEGES ON CATALOG eurostream TO `account users`;\n")
        (Path(d) / "databricks.yml").write_text("run_as:\n  user_name: someone@corp.com\n"
                                                "conf:\n  password: 'hunter2hunter2'\n  salt: '{{secrets/eurostream/pii_salt}}'\n")
        iac = posture.from_iac(d)
        assert iac["VX-UC-1"]["locator"] == "50_grants.sql:2"
        assert iac["GOV-42"]["locator"] == "databricks.yml:2"
        assert iac["VX-SEC-1"]["locator"] == "databricks.yml:4" and "hunter2" not in iac["VX-SEC-1"]["observed"]


def test_non_admin_never_passes_a_list():
    def reader(path):
        if path == "/api/2.0/preview/scim/v2/Me":
            return True, {"groups": [{"display": "users"}]}
        if path == "/api/2.2/jobs/list?limit=100":
            return True, {}                                              # sees no jobs — not "there are none"
        if path.startswith("/api/2.0/preview/workspace-conf"):
            return False, "Error: Forbidden"
        return fetch(path)
    with tempfile.TemporaryDirectory() as d:
        results, _ = posture.run(args(d), fetch=reader)
        assert results["GOV-42"]["status"] == "not_assessed" and "admin read" in results["GOV-42"]["reason"]
        assert results["DP-5"]["reason"].startswith("permission")
        assert results["GOV-35"]["status"] == "fail"                      # a setting it CAN read still counts


def test_identity_client_file_and_revoke():
    import zipfile
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # the client's admin ran the bundle: their live observations count, their not-assessed rows do not
        posture.run(args(d / "client", read_as="user-login"), fetch=fetch)
        client = json.loads((d / "client" / "posture.json").read_text())
        assert client["identity"] == {"name": "eurostream-ci", "id": None, "is_admin": True, "read_as": "user-login"}
        results, _ = posture.run(args(d / "ours", workspace=False, from_posture=str(d / "client" / "posture.json")))
        assert results["GOV-35"]["status"] == "fail" and results["GOV-35"]["source"] == "client"
        assert "sha256" in results["GOV-35"]["locator"] and results["NS-3"]["status"] == "not_assessed"
        assert json.loads((d / "ours" / "readiness.jsonl").read_text())["basis"] == "workspace"
        assert json.loads((d / "ours" / "manifest.json").read_text())["sources_read"][0]["sha256"]
        # a temporary admin grant still in place → a high finding, not a blocked report
        run = d / "client"
        assert posture.verify_revoked(run, posture.Workspace(fetch)) is True
        ids = [json.loads(x)["id"] for x in (run / "findings.jsonl").read_text().splitlines()]
        assert ids.count("FND-SEC-VX-ID-1") == 1
        revoked = posture.Workspace(lambda p: (True, {"displayName": "eurostream-ci", "groups": [{"display": "users"}]}))
        assert posture.verify_revoked(run, revoked) is False
        assert "FND-SEC-VX-ID-1" not in (run / "findings.jsonl").read_text()
        assert "Admin removed" in json.loads((run / "readiness.jsonl").read_text())["rationale"]
        names = zipfile.ZipFile(posture.bundle(d / "b")).namelist()
        assert {"velox-posture/scripts/posture.py", "velox-posture/references/sat-checks.json", "velox-posture/RUN.md"} <= set(names)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
