"""python3 test_build.py — offline check of build_deliverables.py: DRAFT banner only with --include-unreviewed,
and open-question counting (reviewed = still open; answered / rejected = closed)."""
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
    root = tmp / "discovery" / "proj"
    reg, run = root / "registers", root / "runs" / "2026-10-07_run-01"
    # every register, one record per status the Review tab writes
    for name in ("requirements", "findings", "inventory", "business_rules"):
        write(reg / f"{name}.jsonl", [rec(f"{name}-{s}", s, severity="high", category="logic", kind="table")
                                      for s in ("reviewed", "confirmed", "deferred", "rejected")])
        write(run / f"{name}.jsonl", [rec(f"{name}-extracted", "extracted", severity="high", category="logic", kind="table")])
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
print("test_build: ok")
