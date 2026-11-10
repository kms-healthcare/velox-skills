"""python3 test_build.py — offline check of build_deliverables.py: DRAFT banner only with --include-unreviewed,
open-question counting (reviewed = still open; answered / rejected = closed), and the cost section a cost review
adds (velox-spec databricks-cost-review)."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = [{"source_id": "src-1", "locator": "a.sql:1", "kind": "stated"}]


def rec(i, status, **kw):
    return {"id": f"X-{i}", "title": f"t{i}", "name": f"t{i}", "evidence": EV, "status": status, **kw}


def write(p, recs):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in recs))


def project(tmp):
    root = tmp / "assessment" / "proj"
    reg, run = root / "registers", root / "runs" / "2026-10-07_run-01"
    # every register, one record per status the Review tab writes
    for name in ("requirements", "findings", "inventory", "business_rules"):
        write(reg / f"{name}.jsonl", [rec(f"{name}-{s}", s, severity="high", category="logic", kind="table")
                                      for s in ("reviewed", "confirmed", "deferred", "rejected")])
        write(run / f"{name}.jsonl", [rec(f"{name}-extracted", "extracted", severity="high", category="logic", kind="table")])
    write(reg / "findings.jsonl", [rec(f"findings-none-{s}", "confirmed", severity=s, category="logic", migration_disposition="none")
                                   for s in ("high", "low")])
    write(reg / "rationalization.jsonl", [{"object_id": "obj-1", "name": "T", "kind": "table", "disposition": "migrate",
                                           "evidence": EV, "status": "reviewed"}])
    write(reg / "readiness.jsonl", [{"id": "RDY-data", "dimension": "data", "score": 3, "basis": "code",
                                     "rationale": "r", "evidence": EV, "status": "reviewed"}])
    q = lambda i, st, ans=None: {"id": f"OQ-{i}", "question": f"q{i}?", "why": "w", "ask": "Owner (name: ?)", "default": "d",
                                "impact_if_wrong": "high", "blocking": [], "evidence": EV, "status": st, "answer": ans}
    write(reg / "open_questions.jsonl", [q(1, "open"), q(2, "reviewed"), q(3, "answered", "yes"), q(4, "rejected")])
    write(run / "open_questions.jsonl", [q(5, "extracted")])
    (root / "intake.md").write_text("# Intake\n> This report is for X to decide Y.\n")
    (root / "sufficiency.md").write_text("| a |\n")
    return root


def build(root, *flags):
    out = root.parent / ("out-" + ("draft" if flags else "final"))
    subprocess.run([sys.executable, str(HERE / "build_deliverables.py"), str(root), "--out-dir", str(out),
                    "--no-docx", *flags], check=True, capture_output=True)
    return (out / "assessment-report.md").read_text()


def open_ids(md):
    sec = md.split("## C. Stakeholder questionnaire")[1]
    return set(re.findall(r"- (OQ-\d+):", sec))


with tempfile.TemporaryDirectory() as d:
    root = project(Path(d))
    draft, final = build(root, "--include-unreviewed"), build(root)

    assert "— DRAFT, unreviewed" in draft.splitlines()[0], draft.splitlines()[0]
    # 4 registers × 1 extracted record + 1 extracted question
    assert "Draft built from 5 unreviewed records" in draft, draft[:400]
    assert "DRAFT" not in final and "Draft built" not in final

    assert open_ids(final) == {"OQ-1", "OQ-2"}, open_ids(final)          # reviewed stays open; answered/rejected closed
    assert open_ids(draft) == {"OQ-1", "OQ-2", "OQ-5"}, open_ids(draft)
    assert "OQ-4" not in final and "OQ-3" not in open_ids(final)
    assert "X-findings-extracted" in draft and "X-findings-extracted" not in final
    assert "X-findings-rejected" not in draft
    assert "X-findings-none-low" not in final and "none 2" in final                  # changes nothing in the migration: counted, not listed
    assert "X-findings-none-high" in final                                           # ...but a high finding is never hidden

# ---------- the cost section (velox-spec databricks-cost-review) ----------
def cost_project(tmp):
    root = tmp / "assessment" / "tetra"
    reg, run = root / "registers", root / "runs" / "2026-11-05_run-02-hieunle"
    dev = root / "system-tables" / "2026-11-05" / "dev"
    dev.mkdir(parents=True)
    common = {"since": "2026-10-06", "until": "2026-11-05", "workspace_id": "1", "source": "fact", "price": "list", "currency": "USD"}
    views = {
        "cost_by_day": [{"usage_date": "2026-11-01", "product": "JOBS", "usage_unit": "DBU", "quantity": 100.0, "dbu": 100.0, "list_cost": 30.0},
                        {"usage_date": "2026-11-02", "product": "SQL", "usage_unit": "DBU", "quantity": 20.5, "dbu": 20.5, "list_cost": 14.35}],
        "cost_by_job": [{"job_id": "101", "usage_unit": "DBU", "quantity": 90.0, "dbu": 90.0, "list_cost": 27.0}],
        "cost_by_warehouse": [{"warehouse_id": "8d17", "usage_unit": "DBU", "quantity": 20.5, "dbu": 20.5, "list_cost": 14.35}],
        "jobs": [{"job_id": "101", "name": "nightly_orders", "runs": 30, "dbu": 90.0, "list_cost": 27.0, "code": None, "note": None}],
    }
    for v, rows in views.items():
        (dev / f"{v}.json").write_text(json.dumps({"view": v, "rows": rows, **common}))
    (dev / "queries_by_warehouse.json").write_text(json.dumps({"view": "queries_by_warehouse",
        "refused": "Velox cannot read system.query.history: an account admin enables system.query if it is not enabled."}))
    staging = root / "system-tables" / "2026-11-05" / "staging"
    staging.mkdir()
    for v in ("cost_by_day", "jobs"):
        (staging / f"{v}.json").write_text(json.dumps({"view": v, "refused": "Velox cannot read system.billing.usage: grant it."}))
    run.mkdir(parents=True)
    # Velox's own list of what it could not measure; the agent's cost_scope.json names a workspace never reviewed.
    (root / "system-tables" / "2026-11-05" / "not_measured.json").write_text(
        json.dumps({"not_measured": [{"workspace": "PROD", "reason": "Velox not installed"}]}))
    (run / "cost_scope.json").write_text(json.dumps({"not_measured": [{"workspace": "QA", "reason": "made up by the agent"}]}))
    cev = [{"source_id": "src-st", "locator": "assessment/tetra/system-tables/2026-11-05/dev/jobs.json:4", "kind": "stated"}]
    f = lambda i, sev, disp, cat="cost": {"id": f"FND-COST-{i}", "title": f"cost {i}", "severity": sev, "category": cat,
                                          "migration_disposition": disp, "evidence": cev, "status": "confirmed",
                                          "saving": {"amount": 43, "currency": "USD", "per": "day"}}
    text_saving = {**f("text-saving", "high", None), "saving": {"amount": "43", "currency": "USD", "per": "day"}}
    write(reg / "findings.jsonl", [f("high-none", "high", "none"), f("low-none", "low", "none"), f("medium", "medium", None),
                                   f("perf", "low", None, "performance"), text_saving])
    (root / "intake.md").write_text("# Intake\n")
    return root


with tempfile.TemporaryDirectory() as d:
    root = cost_project(Path(d))
    md = build(root)
    sec = md.split("## 8a. Cost & performance")[1].split("\n## 9.")[0]
    # The report's cost section says what it rests on: DEV, the 30 days, DBU and cost at list price, top jobs and warehouses.
    assert "**DEV** — 2026-10-06 to 2026-11-05: 120.5 DBU, 44.35 USD at list price, not the client's rates" in sec, sec
    assert "nightly_orders" in sec and "8d17" in sec, sec
    assert "DEV's queries_by_warehouse was not read: Velox cannot read system.query.history" in sec, sec
    # A workspace not measured is named: one the run says had no Velox, one whose app refused every view.
    assert "PROD: not measured: Velox not installed." in sec, sec
    assert "STAGING: not measured: Velox cannot read system.billing.usage: grant it." in sec, sec
    assert "QA" not in sec, sec                                                      # the agent's file is not read when Velox saved its own
    # Only findings that change a decision: a low `none` stays in the workbook, a high `none` stays in the report.
    assert "FND-COST-high-none" in sec and "FND-COST-medium" in sec and "FND-COST-perf" in sec, sec
    assert "FND-COST-low-none" not in md
    assert "about 43 USD a day, at list price, an estimate" in sec, sec
    # A saving written as text ("43") is not formatted, and does not cost the rest of the report.
    row = next(l for l in sec.splitlines() if "FND-COST-text-saving" in l)
    assert "about" not in row, row
    # Not listed twice: cost findings leave the debt table when the cost section carries them.
    debt = md.split("## 8. Technical debt register")[1].split("## 8a.")[0]
    assert "FND-COST-medium" not in debt, debt
    from openpyxl import load_workbook
    wb = load_workbook(root.parent / "out-final" / "discovery-tetra.xlsx")
    assert any(c.value == "FND-COST-low-none" for row in wb["Findings"].iter_rows() for c in row), "kept in the workbook"

with tempfile.TemporaryDirectory() as d:
    # Reads saved before the desktop wrote not_measured.json: the run's cost_scope.json still names what was not measured.
    root = cost_project(Path(d))
    (root / "system-tables" / "2026-11-05" / "not_measured.json").unlink()
    sec = build(root).split("## 8a. Cost & performance")[1].split("\n## 9.")[0]
    assert "QA: not measured: made up by the agent." in sec and "PROD: not measured" not in sec, sec

with tempfile.TemporaryDirectory() as d:
    # No cost review: no cost section.
    assert "## 8a." not in build(project(Path(d)))
print("test_build: ok")
