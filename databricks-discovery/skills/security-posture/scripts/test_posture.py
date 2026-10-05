"""python3 test_posture.py — offline checks of posture.py against a canned workspace (no network)."""
import argparse
import json
import tempfile
from pathlib import Path

import posture

TIER = "Error: These keys are not available for your pricing tier: [\"enableIpAccessLists\"]"
WORKSPACE = {
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
                cloud="aws", allowed_regions=None)
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
        assert rdy["basis"] == "workspace" and rdy["score"] == score and score <= 3   # a high failure caps at 3
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
