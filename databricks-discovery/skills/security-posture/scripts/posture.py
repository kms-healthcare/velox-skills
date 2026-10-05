#!/usr/bin/env python3
"""Score a Databricks workspace's security posture against SAT's check catalog — read-only.

  python3 posture.py catalog                                   # what is checked, and how
  python3 posture.py run --out <run dir> [--workspace] [--profile P] [--cli databricks]
                         [--sat-results rows.json] [--iac <repo path>] [--allowed-regions REGEX]
  python3 posture.py sat-sql --catalog <sat catalog> --workspace-id <id>   # SQL whose rows feed --sat-results
  python3 posture.py identity [--profile P]                    # who the CLI reads as, and whether it is a workspace admin
  python3 posture.py verify-revoked --run <run dir> [--profile P]   # after a temporary admin grant: warn if it is still there
  python3 posture.py bundle --out <dir>                        # a zip a client's admin runs, for --from-posture

Sources, in the order a check takes its answer from:
  --workspace     live: `databricks api get` on workspace REST (GET only — nothing is changed)
  --sat-results   rows of SAT's own `security_analysis.security_checks` (the client already runs SAT)
  --iac           Terraform / bundle / SQL files: design-time, so it never scores on its own

Writes into --out: posture.json (every check: pass | fail | not_assessed + reason),
findings.jsonl (one FND-SEC-<check_id> per failed check), readiness.jsonl (RDY-security), and
adds every call to manifest.json `external_access`. The score is computed here, never by the agent.
Check ids are SAT's (references/sat-checks.json); VX-* are checks SAT does not have. Stdlib only.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = json.loads((HERE.parent / "references" / "sat-checks.json").read_text())["checks"]
WEIGHT = {"high": 3, "medium": 2, "low": 1}
MIN_COVERAGE = 0.5
NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)
DAY_MS = 86_400_000

VELOX_CHECKS = [
    {"check_id": "VX-IA-1", "title": "Maximum lifetime of new tokens is 90 days or less", "category": "Identity & Access",
     "severity": "medium", "scope": "workspace", "doc": {"aws": "https://docs.databricks.com/aws/en/admin/access-control/tokens"},
     "recommendation": "Set maxTokenLifetimeDays to 90 or less; SAT IA-5 only checks that a limit exists"},
    {"check_id": "VX-UC-1", "title": "No broad write or manage grants to all users", "category": "Governance",
     "severity": "high", "scope": "workspace", "doc": {"aws": "https://docs.databricks.com/aws/en/data-governance/unity-catalog/manage-privileges/"},
     "recommendation": "Grant ALL PRIVILEGES / MODIFY / MANAGE / CREATE to named groups, never to `account users` or `users`"},
    {"check_id": "VX-RES-1", "title": "Metastore region satisfies the residency requirement", "category": "Data Protection",
     "severity": "high", "scope": "workspace", "doc": {"aws": "https://docs.databricks.com/aws/en/resources/supported-regions"},
     "recommendation": "Place the metastore and workspace in a region the residency requirement allows"},
    {"check_id": "VX-ID-1", "title": "The assessment identity holds no workspace admin after the assessment",
     "category": "Identity & Access", "severity": "high", "scope": "session",
     "doc": {"aws": "https://docs.databricks.com/aws/en/admin/users-groups/service-principals"},
     "recommendation": "Remove the assessment service principal from `admins` once the posture read is done"},
    {"check_id": "VX-SEC-1", "title": "No plaintext credentials in infrastructure code", "category": "Data Protection",
     "severity": "high", "scope": "iac", "doc": {"aws": "https://docs.databricks.com/aws/en/security/secrets/"},
     "recommendation": "Read credentials from a secret scope or the CI secret store, never from the repository"},
]
CHECKS = {c["check_id"]: c for c in CATALOG + VELOX_CHECKS}

# workspace-conf keys: (check id, wanted value, platform default when the key is unset or None if not documented)
CONF = {
    "DP-5": ("enableResultsDownloading", "false", "true"),
    "DP-6": ("enableExportNotebook", "false", "true"),
    "DP-7": ("enableNotebookTableClipboard", "false", "true"),
    "DP-8": ("storeInteractiveNotebookResultsInCustomerAccount", "true", "false"),
    "DP-9": ("enableFileStoreEndpoint", "false", None),
    "DP-13": ("enableDbfsFileBrowser", "false", "false"),
    "GOV-14": ("enableEnforceImdsV2", "true", None),
    "GOV-15": ("enableVerboseAuditLogs", "true", "false"),
    "INFO-8": ("enableJobViewAcls", "true", None),
    "INFO-9": ("enforceClusterViewAcls", "true", None),
    "INFO-10": ("enforceWorkspaceViewAcls", "true", None),
    "INFO-11": ("enableProjectTypeInWorkspace", "true", None),
    "INFO-42": ("enableProjectsAllowList", "true", "false"),
    "NS-11": ("enableIpAccessLists", "true", "false"),
}
BROAD_PRINCIPALS = {"account users", "users"}
# Checks that judge a LIST. A non-admin sees only what it was granted, so an empty or clean list is
# not evidence: from such an identity these can fail (what it saw is real) but never pass.
LIST_CHECKS = {"DP-1", "DP-2", "GOV-2", "GOV-5", "GOV-12", "GOV-18", "GOV-19", "GOV-42", "GOV-45",
               "IA-4", "IA-6", "INFO-5", "NS-7", "VX-UC-1"}
PARTIAL = "pass over what this identity can see only; needs a workspace admin read"
BROAD_PRIVS = re.compile(r"ALL[_ ]PRIVILEGES|MODIFY|MANAGE|CREATE", re.I)


def result(status, observed="", locator="", reason=None, source="workspace"):
    return {"status": status, "observed": str(observed)[:300], "locator": locator, "reason": reason, "source": source}


def na(reason, observed=""):
    return result("not_assessed", observed, reason=reason)


# ---------- live workspace ----------
class Workspace:
    """`databricks api get`, cached. Every call is recorded for manifest.json."""

    def __init__(self, fetch):
        self.fetch, self.cache, self.calls = fetch, {}, []

    @property
    def is_admin(self):
        """Member of the workspace `admins` group. Unknown counts as no: a guess must not turn into a pass."""
        ok, me = self.get("/api/2.0/preview/scim/v2/Me")
        return ok and any(g.get("display") == "admins" for g in me.get("groups", []))

    def get(self, path):
        if path not in self.cache:
            ok, body = self.fetch(path)
            self.cache[path] = (ok, body)
            self.calls.append({"endpoint": f"GET {path}", "ok": ok})
        return self.cache[path]


def cli_fetch(cli, profile):
    def fetch(path):
        cmd = [cli, "api", "get", path, "-o", "json"] + (["-p", profile] if profile else [])
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout).strip().splitlines()[0] if (p.stderr or p.stdout).strip() else f"exit {p.returncode}"
        try:
            return True, json.loads(p.stdout or "{}")
        except json.JSONDecodeError:
            return False, "unparseable response"
    return fetch


def failure(body):
    """Why a GET failed, as a not-assessed reason."""
    text = str(body)
    if re.search(r"pricing tier|not available|unavailable_for", text, re.I):
        return na("not available on this pricing tier", text)
    if re.search(r"PERMISSION_DENIED|403|Forbidden|not authorized|permission|admin", text, re.I):
        return na("permission: the identity cannot read this", text)
    return na("error", text)


def conf_check(ws, key, want, default):
    path = f"/api/2.0/preview/workspace-conf?keys={key}"
    ok, body = ws.get(path)
    if not ok:
        return failure(body)
    value = body.get(key) if isinstance(body, dict) else None
    shown = value
    if value in (None, ""):
        if default is None:
            return na("unset; platform default not documented here", f"{key} unset")
        value, shown = default, f"unset (platform default {default})"
    return result("pass" if str(value).lower() == want else "fail", f"{key}={shown}", f"GET {path} → {key}={shown}")


def setting(ws, name):
    path = f"/api/2.0/settings/types/{name}/names/default"
    ok, body = ws.get(path)
    return path, ok, body


def bool_setting(ws, name, field, inner, want):
    path, ok, body = setting(ws, name)
    if not ok:
        return failure(body)
    block = body.get(field, {}) or {}
    details = block.get("enablement_details", {}) or {}
    if any(v for k, v in details.items() if k.startswith("unavailable")):
        return na("not available on this pricing tier", f"{field}.enablement_details={details}")
    value = block.get(inner)
    return result("pass" if value is want else "fail", f"{field}.{inner}={value}", f"GET {path} → {field}.{inner}={value}")


def tokens(ws):
    ok, body = ws.get("/api/2.0/token/list")
    return (body.get("token_infos", []) if ok else None), body


def clusters(ws):
    ok, body = ws.get("/api/2.0/clusters/list")
    return (body.get("clusters", []) if ok else None), body


def jobs(ws, cap=50):
    ok, body = ws.get("/api/2.2/jobs/list?limit=100")
    return (body.get("jobs", [])[:cap] if ok else None), body


def metastore(ws):
    ok, body = ws.get("/api/2.1/unity-catalog/metastore_summary")
    return (body if ok else None), body


def check_workspace(ws, cid, allowed_regions):
    if cid in CONF:
        return conf_check(ws, *CONF[cid])
    if cid == "IA-5" or cid == "VX-IA-1":
        r = conf_check(ws, "maxTokenLifetimeDays", "__any__", None)
        if r["status"] == "not_assessed" and "unset" in r["observed"]:
            return result("fail", "maxTokenLifetimeDays unset (unlimited)", r["locator"] or
                          "GET /api/2.0/preview/workspace-conf?keys=maxTokenLifetimeDays → unset")
        if r["status"] == "not_assessed":
            return r
        days = int(re.sub(r"\D", "", r["observed"].split("=")[1]) or 0)
        ok = days > 0 if cid == "IA-5" else 0 < days <= 90
        return result("pass" if ok else "fail", f"maxTokenLifetimeDays={days}", r["locator"])
    if cid in ("GOV-2", "IA-4", "IA-6"):
        infos, body = tokens(ws)
        if infos is None:
            return failure(body)
        loc = "GET /api/2.0/token/list"
        if cid == "GOV-2":
            soon = [t.get("comment") or t.get("token_id") for t in infos
                    if t.get("expiry_time", -1) > 0 and t["expiry_time"] - NOW_MS < 7 * DAY_MS]
            return result("fail" if soon else "pass", f"{len(infos)} tokens; expiring ≤7d: {soon[:5]}", loc)
        if cid == "IA-4":
            bad = [t.get("comment") or t.get("token_id") for t in infos
                   if t.get("expiry_time", -1) <= 0 or t["expiry_time"] - t.get("creation_time", NOW_MS) > 90 * DAY_MS]
            return result("fail" if bad else "pass", f"{len(infos)} tokens; no expiry or >90d: {bad[:5]}", loc)
        r = conf_check(ws, "maxTokenLifetimeDays", "__any__", None)
        limit = int(re.sub(r"\D", "", r["observed"].split("=")[-1]) or 0) if r["status"] != "not_assessed" else 0
        if not limit:
            return na("no workspace maximum to compare against", r["observed"])
        bad = [t.get("comment") or t.get("token_id") for t in infos
               if t.get("expiry_time", -1) <= 0 or t["expiry_time"] - t.get("creation_time", NOW_MS) > limit * DAY_MS]
        return result("fail" if bad else "pass", f"{len(infos)} tokens; over {limit}d: {bad[:5]}", loc)
    if cid == "IA-8":
        path = "/api/2.0/permissions/authorization/tokens"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        groups = [a.get("group_name") for a in body.get("access_control_list", [])]
        return result("fail" if "users" in groups else "pass", f"token ACL groups: {groups}", f"GET {path}")
    if cid in ("DP-2", "GOV-5", "GOV-12"):
        cl, body = clusters(ws)
        if cl is None:
            return failure(body)
        loc = "GET /api/2.0/clusters/list"
        if not cl:
            return result("pass", "0 classic clusters", loc)
        if cid == "DP-2":
            bad = [c.get("cluster_name") for c in cl if c.get("enable_local_disk_encryption") is False]
        elif cid == "GOV-12":
            bad = [c.get("cluster_name") for c in cl if c.get("data_security_mode") in (None, "NONE", "LEGACY_PASSTHROUGH",
                                                                                          "LEGACY_TABLE_ACL", "LEGACY_SINGLE_USER")]
        else:
            ok, sv = ws.get("/api/2.0/clusters/spark-versions")
            if not ok:
                return failure(sv)
            supported = {v.get("key") for v in sv.get("versions", [])}
            bad = [f"{c.get('cluster_name')} ({c.get('spark_version')})" for c in cl if c.get("spark_version") not in supported]
        return result("fail" if bad else "pass", f"{len(cl)} clusters; failing: {bad[:5]}", loc)
    if cid in ("GOV-42", "GOV-45"):
        js, body = jobs(ws)
        if js is None:
            return failure(body)
        loc = "GET /api/2.2/jobs/list"
        if cid == "GOV-42":
            bad = [j.get("settings", {}).get("name") for j in js if "@" in str(j.get("run_as_user_name") or "")]
            return result("fail" if bad else "pass", f"{len(js)} jobs; run as a person: {bad[:5]}", loc)
        bad = []
        for j in js:
            ok, acl = ws.get(f"/api/2.0/permissions/jobs/{j.get('job_id')}")
            if not ok:
                return failure(acl)
            for a in acl.get("access_control_list", []):
                manage = any(p.get("permission_level") == "CAN_MANAGE" and not p.get("inherited")
                             for p in a.get("all_permissions", []))
                who = a.get("group_name") or a.get("user_name") or a.get("service_principal_name")
                if manage and who not in ("admins", j.get("creator_user_name")):
                    bad.append(f"{j.get('settings', {}).get('name')}: {who}")
        return result("fail" if bad else "pass", f"{len(js)} jobs; CAN_MANAGE to non-admins: {bad[:5]}",
                      "GET /api/2.0/permissions/jobs/{job_id}")
    if cid == "INFO-5":
        path = "/api/2.0/global-init-scripts"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        scripts = [s.get("name") for s in body.get("scripts", [])]
        return result("fail" if scripts else "pass", f"global init scripts: {scripts[:5]}", f"GET {path}")
    if cid == "INFO-6":
        path = "/api/2.0/preview/scim/v2/Groups?filter=" + urllib.parse.quote('displayName eq "admins"')
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        members = sum(len(g.get("members", [])) for g in body.get("Resources", []))
        return result("fail" if members > 2 else "pass", f"admins: {members} members", f"GET {path}")
    if cid == "DP-1":
        path = "/api/2.0/secrets/scopes/list"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        scopes = [s.get("name") for s in body.get("scopes", [])]
        return result("pass" if scopes else "fail", f"secret scopes: {scopes[:5]}", f"GET {path}")
    if cid == "NS-5":
        path = "/api/2.0/ip-access-lists"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        lists = [x for x in body.get("ip_access_lists", []) if x.get("enabled")]
        return result("pass" if lists else "fail", f"{len(lists)} enabled IP access lists", f"GET {path}")
    if cid == "NS-7":
        path = "/api/2.0/serving-endpoints"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        # Databricks-hosted foundation models are not the workspace's own endpoints
        eps = [e.get("name") for e in body.get("endpoints", []) if e.get("endpoint_type") != "FOUNDATION_MODEL_API"]
        if not eps:
            return result("pass", "0 custom serving endpoints", f"GET {path}")
        ip = conf_check(ws, *CONF["NS-11"])
        if ip["status"] == "not_assessed":
            return ip
        return result("pass" if ip["status"] == "pass" else "fail",
                      f"{len(eps)} serving endpoints; IP access lists: {ip['observed']}", f"GET {path}")
    if cid == "DP-10":
        path, ok, body = setting(ws, "disable_legacy_dbfs")
        if not ok:
            return failure(body)
        v = (body.get("disable_legacy_dbfs") or {}).get("value")
        return result("pass" if v is True else "fail", f"disable_legacy_dbfs={v}", f"GET {path}")
    if cid == "DP-11":
        path, ok, body = setting(ws, "sql_results_download")
        if not ok:
            return failure(body)
        v = (body.get("boolean_val") or {}).get("value")
        return result("pass" if v is False else "fail", f"sql_results_download={v}", f"GET {path}")
    if cid == "GOV-35":
        path, ok, body = setting(ws, "restrict_workspace_admins")
        if not ok:
            return failure(body)
        v = (body.get("restrict_workspace_admins") or {}).get("status")
        return result("fail" if v == "ALLOW_ALL" else "pass", f"restrict_workspace_admins.status={v}", f"GET {path}")
    if cid == "GOV-36":
        return bool_setting(ws, "automatic_cluster_update", "automatic_cluster_update_workspace", "enabled", True)
    if cid == "INFO-39":
        return bool_setting(ws, "shield_csp_enablement_ws_db", "compliance_security_profile_workspace", "is_enabled", True)
    if cid == "INFO-40":
        return bool_setting(ws, "shield_esm_enablement_ws_db", "enhanced_security_monitoring_workspace", "is_enabled", True)
    if cid in ("GOV-16", "GOV-20"):
        path = "/api/2.1/unity-catalog/current-metastore-assignment"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        mid = body.get("metastore_id")
        return result("pass" if mid else "fail", f"metastore_id={mid}", f"GET {path}")
    if cid in ("GOV-17", "GOV-21", "GOV-34", "VX-RES-1"):
        ms, body = metastore(ws)
        if ms is None:
            return failure(body)
        loc = "GET /api/2.1/unity-catalog/metastore_summary"
        if cid == "GOV-17":
            life = ms.get("delta_sharing_recipient_token_lifetime_in_seconds") or 0
            bad = ms.get("delta_sharing_scope") == "INTERNAL_AND_EXTERNAL" and (life == 0 or life > 90 * 86400)
            return result("fail" if bad else "pass", f"delta_sharing_scope={ms.get('delta_sharing_scope')}, lifetime={life}s", loc)
        if cid == "GOV-21":
            owner = ms.get("owner")
            bad = owner == ms.get("created_by") or "@" in str(owner) or owner == "System user"
            return result("fail" if bad else "pass", f"owner={owner}, created_by={ms.get('created_by')}", loc)
        if cid == "VX-RES-1":
            if not allowed_regions:
                return na("no residency requirement given (--allowed-regions)", f"region={ms.get('region')}")
            region = ms.get("region") or ""
            return result("pass" if re.search(allowed_regions, region) else "fail",
                          f"metastore region={region}; allowed /{allowed_regions}/", loc)
        path = f"/api/2.1/unity-catalog/metastores/{ms.get('metastore_id')}/systemschemas"
        ok, sys_ = ws.get(path)
        if not ok:
            return failure(sys_)
        access = next((s.get("state") for s in sys_.get("schemas", []) if s.get("schema") == "access"), None)
        enabled = str(access).upper().startswith("ENABLE") or str(access).upper() == "MANAGED"  # MANAGED = enabled by Databricks
        return result("pass" if enabled else "fail", f"system schema access: {access}", f"GET {path}")
    if cid in ("GOV-18", "GOV-19"):
        path = "/api/2.1/unity-catalog/recipients"
        ok, body = ws.get(path)
        if not ok:
            return failure(body)
        rec = [r for r in body.get("recipients", []) if r.get("authentication_type") == "TOKEN"]
        if cid == "GOV-18":
            bad = [r.get("name") for r in rec if not (r.get("ip_access_list") or {}).get("allowed_ip_addresses")]
        else:
            bad = [r.get("name") for r in rec if any(not t.get("expiration_time") for t in r.get("tokens", []))]
        return result("fail" if bad else "pass", f"{len(rec)} token recipients; failing: {bad[:5]}", f"GET {path}")
    if cid == "VX-UC-1":
        ok, body = ws.get("/api/2.1/unity-catalog/catalogs")
        if not ok:
            return failure(body)
        bad, seen = [], 0
        for c in body.get("catalogs", []):
            name = c.get("name")
            if name in ("system", "samples") or c.get("catalog_type") in ("SYSTEM_CATALOG", "DELTASHARING_CATALOG"):
                continue
            targets = [("catalog", name)]
            ok_s, sch = ws.get(f"/api/2.1/unity-catalog/schemas?catalog_name={urllib.parse.quote(name)}")
            if ok_s:
                targets += [("schema", s.get("full_name")) for s in sch.get("schemas", [])[:50]
                            if s.get("name") != "information_schema"]
            for kind, full in targets:
                ok_p, perms = ws.get(f"/api/2.1/unity-catalog/permissions/{kind}/{urllib.parse.quote(full)}")
                if not ok_p:
                    continue
                seen += 1
                for a in perms.get("privilege_assignments", []):
                    privs = [p for p in a.get("privileges", []) if BROAD_PRIVS.search(p)]
                    if a.get("principal") in BROAD_PRINCIPALS and privs:
                        bad.append(f"{kind} {full}: {a['principal']} {privs}")
        if not seen:
            return na("permission: no grants readable", "0 securables readable")
        return result("fail" if bad else "pass", f"{seen} securables; broad grants: {bad[:5]}",
                      "GET /api/2.1/unity-catalog/permissions/{catalog|schema}/{name}")
    return None


# ---------- SAT results ----------
def sat_sql(catalog, workspace_id):
    s = f"`{catalog}`.security_analysis"
    return (f"SELECT b.check_id, c.score, c.additional_details, c.run_id, c.check_time\n"
            f"FROM {s}.security_checks c JOIN {s}.security_best_practices b ON c.id = b.id\n"
            f"WHERE c.workspaceid = '{workspace_id}'\n"
            f"  AND c.run_id = (SELECT max(run_id) FROM {s}.security_checks WHERE workspaceid = '{workspace_id}')")


def from_sat(rows, table="security_analysis.security_checks"):
    """SAT writes score 0 = passed, 1 = violation found (security_checks column comment, SAT 0.9.0)."""
    out = {}
    for r in rows:
        cid = r.get("check_id")
        if cid not in CHECKS or r.get("score") is None:
            continue
        details = r.get("additional_details") or {}
        out[cid] = result("fail" if int(r["score"]) else "pass", json.dumps(details)[:300] if details else "",
                          f"{table} run_id={r.get('run_id')} check_id={cid}", source="sat")
    return out


# ---------- infrastructure code ----------
IAC_FILES = ("*.tf", "*.yml", "*.yaml", "*.sql", "*.json", "*.py")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".terraform"}
SECRET_RE = re.compile(r"""(client_secret|password|api_key|access_token|secret)\s*[:=]\s*["']([^"'${}\s]{8,})["']""", re.I)
PAT_RE = re.compile(r"\bdapi[0-9a-f]{32}\b")
GRANT_RE = re.compile(r"GRANT\s+(.+?)\s+ON\s+.+?\s+TO\s+[`'\"]?(account users|users)[`'\"]?", re.I)


def from_iac(root):
    found = {}  # check id -> list of (locator, observed, status)
    scanned = 0

    def add(cid, status, loc, observed):
        found.setdefault(cid, []).append((status, loc, observed))

    for pattern in IAC_FILES:
        for f in Path(root).rglob(pattern):
            if any(part in SKIP_DIRS for part in f.parts) or f.stat().st_size > 2_000_000:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rel = f.relative_to(root)
            scanned += 1
            for i, line in enumerate(lines, 1):
                loc = f"{rel}:{i}"
                if f.suffix in (".sql", ".py", ".yml", ".yaml", ".tf"):
                    g = GRANT_RE.search(line)
                    if g and BROAD_PRIVS.search(g.group(1)):
                        add("VX-UC-1", "fail", loc, line.strip())
                if re.search(r"principal\s*[:=]\s*[`'\"]?(account users|users)[`'\"]?\s*$", line, re.I):
                    window = " ".join(lines[max(0, i - 4):i + 4])
                    if BROAD_PRIVS.search(window):
                        add("VX-UC-1", "fail", loc, line.strip())
                if "secrets/" not in line and (SECRET_RE.search(line) or PAT_RE.search(line)):
                    add("VX-SEC-1", "fail", loc, re.sub(r"(['\"])[^'\"]{4,}(['\"])", r"\1***\2", line.strip()))
                m = re.search(r"data_security_mode\s*[:=]\s*[\"']?(\w+)", line)
                if m:
                    add("GOV-12", "fail" if re.match(r"NONE|NO_ISOLATION|LEGACY_", m.group(1)) else "pass", loc, line.strip())
                if re.search(r"enable_local_disk_encryption\s*[:=]\s*false", line, re.I):
                    add("DP-2", "fail", loc, line.strip())
                if re.match(r"\s*run_as\s*:", line) and i < len(lines):
                    nxt = lines[i]
                    if re.search(r"user_name\s*:\s*\S+@", nxt):
                        add("GOV-42", "fail", f"{rel}:{i + 1}", nxt.strip())
                    elif re.search(r"(group_name|service_principal_name)\s*:", nxt):
                        add("GOV-42", "pass", f"{rel}:{i + 1}", nxt.strip())
                for cid, (key, want, _) in CONF.items():
                    m = re.search(rf"[\"']?{key}[\"']?\s*[:=]\s*[\"']?(true|false)[\"']?", line, re.I)
                    if m:
                        add(cid, "pass" if m.group(1).lower() == want else "fail", loc, line.strip())
    out = {"_scanned": scanned}
    for cid, hits in found.items():
        fails = [h for h in hits if h[0] == "fail"]
        status, loc, observed = (fails or hits)[0]
        more = f" (+{len(fails) - 1} more)" if len(fails) > 1 else ""
        out[cid] = result(status, observed + more, loc, source="iac")
    return out


# ---------- who reads, and what a client supplied ----------
READ_AS = {"service-principal": "the assessment service principal",
           "elevated-service-principal": "the assessment service principal, temporarily a workspace admin",
           "user-login": "the consultant's own login"}


def whoami(ws):
    ok, me = ws.get("/api/2.0/preview/scim/v2/Me")
    if not ok:
        return {"name": None, "is_admin": None, "error": str(me)[:200]}
    return {"name": me.get("displayName") or me.get("userName"), "id": me.get("userName"), "is_admin": ws.is_admin}


def supplied_meta(path):
    data = Path(path).read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def from_posture(path):
    """Checks a client's admin ran with the bundle. Only what THEY observed live counts; their own
    not-assessed rows stay not assessed here."""
    meta = supplied_meta(path)
    doc = json.loads(Path(path).read_text())
    who = (doc.get("identity") or {}).get("name") or "the client's admin"
    out = {}
    for c in doc.get("checks", []):
        if c.get("check_id") in CHECKS and c.get("source") == "workspace" and c.get("status") in ("pass", "fail"):
            loc = f"{Path(path).name} (sha256 {meta['sha256'][:12]}, read as {who}) → {c.get('locator')}"
            out[c["check_id"]] = result(c["status"], c.get("observed", ""), loc[:200], source="client")
    return out


def verify_revoked(run_dir, ws):
    """After a temporary admin grant: still admin → a high finding in the run (the report warns, it is
    not blocked); revoked → the readiness record says when."""
    me = whoami(ws)
    findings = run_dir / "findings.jsonl"
    rows = [json.loads(x) for x in findings.read_text().splitlines() if x.strip()] if findings.exists() else []
    rows = [f for f in rows if f.get("id") != "FND-SEC-VX-ID-1"]
    stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
    if me["is_admin"] is None:
        print(f"could not tell whether {me.get('name')} is still an admin: {me.get('error')}")
        return None
    if me["is_admin"]:
        r = result("fail", f"{me['name']} is still in the workspace admins group at {stamp}",
                   "GET /api/2.0/preview/scim/v2/Me → groups contains admins")
        f = finding("VX-ID-1", r, "aws")
        f["title"] = f"The assessment service principal {me['name']} still holds workspace admin"[:120]
        f["impact"] = "Velox was promised read-only access; an admin service principal can change or delete anything in the workspace."
        rows.append(f)
        print(f"WARNING: {me['name']} is still a workspace admin — recorded as FND-SEC-VX-ID-1 (high)")
    else:
        rdy_file = run_dir / "readiness.jsonl"
        if rdy_file.exists():
            rdy = json.loads(rdy_file.read_text())
            rdy["rationale"] = f"{rdy['rationale']} Admin removed, checked {stamp}."[:300]
            rdy_file.write_text(json.dumps(rdy, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{me['name']} is no longer a workspace admin (checked {stamp})")
    findings.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in rows), encoding="utf-8")
    return me["is_admin"]


def bundle(out):
    """scripts/posture.py + references/sat-checks.json + RUN.md, zipped, for a client's admin."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "velox-posture"
        (root / "scripts").mkdir(parents=True)
        (root / "references").mkdir()
        shutil.copy(HERE / "posture.py", root / "scripts" / "posture.py")
        shutil.copy(HERE.parent / "references" / "sat-checks.json", root / "references" / "sat-checks.json")
        (root / "RUN.md").write_text(
            "# Databricks security posture — read-only\n\n"
            "Needs Python 3.9+ and the Databricks CLI signed in as a workspace admin. It only reads (GET);\n"
            "it changes nothing. Run:\n\n"
            "    python3 scripts/posture.py run --workspace --profile <your profile> --out result\n\n"
            "Send back `result/posture.json`. It holds settings and check results, no data and no credentials.\n",
            encoding="utf-8")
        out.mkdir(parents=True, exist_ok=True)
        return shutil.make_archive(str(out / "velox-posture"), "zip", d, "velox-posture")


# ---------- scoring and records ----------
def score(results):
    """1–5 from severity-weighted pass share over ASSESSED live/SAT checks; any high failure caps at 3, three cap at 2;
    none under MIN_COVERAGE of the catalog's weight."""
    assessed = {c: r for c, r in results.items() if r["status"] in ("pass", "fail") and r["source"] in ("workspace", "sat", "client")}
    if not assessed:
        return None, 0.0, 0
    w = {c: WEIGHT[CHECKS[c]["severity"]] for c in assessed}
    share = sum(w[c] for c, r in assessed.items() if r["status"] == "pass") / sum(w.values())
    s = 1 + round(4 * share)
    highs = sum(1 for c, r in assessed.items() if r["status"] == "fail" and CHECKS[c]["severity"] == "high")
    s = min(s, 2 if highs >= 3 else 3 if highs else 5)
    total = sum(WEIGHT[c["severity"]] for c in CHECKS.values() if c["scope"] != "iac")
    coverage = round(sum(w.values()) / total, 2)
    # a number over less than half the catalog describes the identity's view, not the workspace
    return (s if coverage >= MIN_COVERAGE else None), coverage, highs


def doc_for(check, cloud="aws"):
    return check.get("doc", {}).get(cloud) or next(iter(check.get("doc", {}).values()), None)


def finding(cid, r, cloud):
    c = CHECKS[cid]
    kind = "stated"
    source_id = {"workspace": "src-workspace-api", "sat": "src-sat", "iac": "src-iac", "client": "src-client-posture"}[r["source"]]
    ev = [{"source_id": source_id, "source_type": r["source"], "locator": r["locator"][:200],
           "excerpt": r["observed"][:120], "kind": kind},
          {"source_id": "ref-sat" if not cid.startswith("VX-") else "ref-databricks-docs", "locator": cid,
           "excerpt": c["recommendation"][:120], "kind": "external", "reference": doc_for(c, cloud)}]
    return {"id": f"FND-SEC-{cid}", "severity": c["severity"], "category": "security",
            "title": f"{c['title']} — not met"[:120],
            "detail": f"{cid} ({c['category']}): {r['observed']}"[:300],
            "impact": f"Deviates from Databricks best practice: {c['recommendation']}"[:300],
            "check_id": cid, "practice_ref": None, "check_source": r["source"],
            "evidence": ev, "requirements_raised": [], "questions_raised": [], "layer": "ops",
            "migration_disposition": None, "confidence": 0.95 if r["source"] != "iac" else 0.8, "status": "extracted"}


def readiness(results, s, coverage, highs):
    na_reasons = {}
    for cid, r in results.items():
        if r["status"] == "not_assessed":
            na_reasons[r["reason"] or "not implemented"] = na_reasons.get(r["reason"] or "not implemented", 0) + 1
    basis = "workspace" if any(r["source"] in ("workspace", "client") and r["status"] != "not_assessed" for r in results.values()) else \
        "sat" if any(r["source"] == "sat" for r in results.values()) else "code"
    passed = sum(1 for r in results.values() if r["status"] == "pass")
    failed = sum(1 for r in results.values() if r["status"] == "fail")
    needs = "; ".join(f"{n} {k}" for k, n in sorted(na_reasons.items(), key=lambda x: -x[1]))
    if s is None and basis != "code" and coverage:
        needs = f"weighted coverage {int(coverage * 100)}% is under {int(MIN_COVERAGE * 100)}% — not scored; " + needs
    return {"id": "RDY-security", "dimension": "security", "score": s if basis != "code" else None, "basis": basis,
            "rationale": f"{passed} checks pass, {failed} fail ({highs} high); weighted coverage {int(coverage * 100)}% of the SAT catalog"[:300],
            "needs": f"not assessed — {needs}" if needs else None,
            "evidence": [{"source_id": "src-posture", "locator": "posture.json", "kind": "stated"}], "status": "extracted"}


def run(args, fetch=None):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results, calls = {}, []
    ws = None
    if args.workspace:
        ws = Workspace(fetch or cli_fetch(args.cli, args.profile))
    sat = from_sat(json.loads(Path(args.sat_results).read_text())) if args.sat_results else {}
    iac = from_iac(args.iac) if args.iac else {}
    scanned = iac.pop("_scanned", 0)
    if args.iac and "VX-SEC-1" not in iac:
        iac["VX-SEC-1"] = result("pass", f"no plaintext credential in {scanned} files", args.iac, source="iac")
    supplied = from_posture(args.from_posture) if args.from_posture else {}
    for cid, c in CHECKS.items():
        if args.cloud not in c.get("clouds", [args.cloud]) or c["scope"] == "session":
            continue
        r = None
        if cid in supplied and supplied[cid]["status"] != "not_assessed":
            r = supplied[cid]
        if r is None and ws and c["scope"] == "workspace":
            r = check_workspace(ws, cid, args.allowed_regions)
            if r and r["status"] == "pass" and cid in LIST_CHECKS and not ws.is_admin:
                r = na(PARTIAL, r["observed"])
        if (r is None or r["status"] == "not_assessed") and cid in sat:
            r = sat[cid]
        if (r is None or r["status"] == "not_assessed") and cid in iac:
            r = iac[cid]
        if r is None:
            reason = {"account": "account-level API: needs account admin, or SAT results",
                      "compute": "needs a run on cluster compute, or SAT results",
                      "iac": "no infrastructure code given (--iac)"}.get(c["scope"], "not implemented in this skill yet")
            if c["scope"] == "workspace" and not ws:
                reason = "no live workspace read (--workspace)"
                if args.iac:
                    reason += "; not settled by infrastructure code"
            r = na(reason)
        results[cid] = r
    identity = whoami(ws) if ws else None
    if identity:
        identity["read_as"] = args.read_as
    if ws:
        calls = ws.calls
    s, coverage, highs = score(results)
    rows = [{"check_id": cid, **{k: CHECKS[cid][k] for k in ("title", "category", "severity", "scope")},
             "doc": doc_for(CHECKS[cid], args.cloud), **r} for cid, r in results.items()]
    (out / "posture.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                                                  "score": s, "weighted_coverage": coverage, "cloud": args.cloud,
                                                  "identity": identity, "supplied": args.from_posture and supplied_meta(args.from_posture),
                                                  "checks": rows}, indent=1), encoding="utf-8")
    fails = [finding(cid, r, args.cloud) for cid, r in results.items() if r["status"] == "fail"]
    (out / "findings.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in fails), encoding="utf-8")
    rdy = readiness(results, s, coverage, highs)
    if identity:
        rdy["rationale"] = f"Read as {identity['name']} ({READ_AS[args.read_as]}). {rdy['rationale']}"[:300]
    elif args.from_posture:
        rdy["rationale"] = f"Read by the client's admin, supplied as {Path(args.from_posture).name}. {rdy['rationale']}"[:300]
    (out / "readiness.jsonl").write_text(json.dumps(rdy, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = out / "manifest.json"
    m = json.loads(manifest.read_text()) if manifest.exists() else {"run_id": out.name, "skill": "security-posture"}
    if args.from_posture:
        m.setdefault("sources_read", []).append({"source_id": "src-client-posture", **supplied_meta(args.from_posture)})
    m.setdefault("external_access", []).extend(
        {"endpoint": c["endpoint"], "statement": None, "rows": None, "ok": c["ok"]} for c in calls)
    manifest.write_text(json.dumps(m, indent=1), encoding="utf-8")
    tally = {k: sum(1 for r in results.values() if r["status"] == k) for k in ("pass", "fail", "not_assessed")}
    print(f"security posture: score {s if s is not None else 'not scored'} / 5 · {tally} · weighted coverage "
          f"{int(coverage * 100)}% · {len(calls)} GET calls")
    for f in sorted(fails, key=lambda f: WEIGHT[f["severity"]], reverse=True)[:10]:
        print(f"  {f['severity']:<6} {f['check_id']:<9} {f['detail'][:110]}")
    return results, s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalog")
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--workspace", action="store_true")
    r.add_argument("--profile")
    r.add_argument("--cli", default="databricks")
    r.add_argument("--sat-results")
    r.add_argument("--iac")
    r.add_argument("--cloud", default="aws", choices=["aws", "azure", "gcp"])
    r.add_argument("--allowed-regions", help="regex the metastore region must match, e.g. '^eu-|europe'")
    r.add_argument("--from-posture", help="posture.json a client's admin produced with the bundle")
    r.add_argument("--read-as", default="service-principal", choices=list(READ_AS))
    i = sub.add_parser("identity")
    v = sub.add_parser("verify-revoked")
    v.add_argument("--run", required=True)
    for x in (i, v):
        x.add_argument("--profile")
        x.add_argument("--cli", default="databricks")
    b = sub.add_parser("bundle")
    b.add_argument("--out", required=True)
    q = sub.add_parser("sat-sql")
    q.add_argument("--catalog", required=True)
    q.add_argument("--workspace-id", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "catalog":
        probe = Workspace(lambda p: (False, "catalog listing"))
        for cid, c in CHECKS.items():
            how = c["scope"] if c["scope"] != "workspace" else (
                "workspace" if check_workspace(probe, cid, None) is not None else "not implemented")
            print(f"{cid:<9} {c['severity']:<6} {how:<16} {c['title']}")
    elif a.cmd == "sat-sql":
        print(sat_sql(a.catalog, a.workspace_id))
    elif a.cmd == "identity":
        print(json.dumps(whoami(Workspace(cli_fetch(a.cli, a.profile)))))
    elif a.cmd == "verify-revoked":
        verify_revoked(Path(a.run), Workspace(cli_fetch(a.cli, a.profile)))
    elif a.cmd == "bundle":
        print(bundle(Path(a.out)))
    else:
        if not (a.workspace or a.sat_results or a.iac or a.from_posture):
            sys.exit("give at least one source: --workspace, --sat-results, --from-posture or --iac")
        run(a)


if __name__ == "__main__":
    main()
