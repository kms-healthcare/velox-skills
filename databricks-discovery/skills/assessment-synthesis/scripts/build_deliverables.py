#!/usr/bin/env python3
"""Generate the human-facing deliverables from discovery registers.

  python3 build_deliverables.py <discovery/project dir> [--out-dir <dir>] [--include-unreviewed]
                                [--author-sections <file.md>] [--no-docx] [--strict-register]

Reads   <project>/registers/*.jsonl (or, with --include-unreviewed, also runs/*/ *.jsonl),
        <project>/intake.md, <project>/sufficiency.md
Writes  <out-dir>/discovery-<project>.xlsx      one workbook, tabs in reading order
        <out-dir>/assessment-report.md          generated; author sections merged from --author-sections
        <out-dir>/assessment-report.docx        via pandoc when available (skip with --no-docx)

Stdlib + openpyxl. Never invents: every number is followed by its locators; unreviewed records
are excluded unless asked for; placeholders like <catalog> are left visible.

Two registers of language. §0–§5 are what a sponsor, a CFO or a business owner reads: no status
code, no register field name, no undefined product name, no ID as the subject of a sentence.
§6 onward is for the architect and the DBA and may use the codes, always next to their plain label.
`--strict-register` turns the check into an error.
"""
import argparse, json, re, shutil, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    sys.exit("openpyxl is required: pip install openpyxl")

REVIEWED = {"reviewed", "confirmed", "deferred"}
SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3}
DISPOSITIONS = ["migrate", "modernize", "retire", "defer"]
# Word budgets for the hand-written sections. The registers cap excerpts and details; without a cap
# here the prose grew to ~1,900 words and pushed the report past the twelve pages the skill argues
# for. Over budget is a warning, not an error — the author decides.
AUTHOR_CAPS = {"summary": 120, "decision": 400, "architecture": 500, "governance": 300,
               "business_case": 250, "success": 150, "drivers": 300, "risks": 400}
AUTHOR_KEYS = tuple(AUTHOR_CAPS)


# ---------- plain language ----------
# The registers use short codes so records diff, group and sort. A client reads the report, not the
# registers, so every code is rendered through these maps. The raw code survives only as a
# parenthetical in the technical half of the report and as a column in the workbook, where it is
# what you filter on. references/plain-language.md is this same table, for humans.
RULE_STATUS_LABEL = {
    "VERIFIED":    "Confirmed — the code and the document agree",
    "CONFLICT":    "Disputed — the code and the document disagree",
    "CODE-ONLY":   "In the code only — no written specification",
    "DOC-ONLY":    "In the specification only — never built",
    "CONFIG-ONLY": "In a configuration value, not in the code",
    "DEAD":        "Not used by anything today",
    "UNRESOLVED":  "Not yet traced to a source",
}
STATUS_LABEL = {"extracted": "Draft", "reviewed": "Checked", "confirmed": "Signed off by owner",
                "deferred": "Deferred", "rejected": "Rejected", "open": "Open", "answered": "Answered"}
DISPOSITION_LABEL = {"migrate": "Move as it is", "modernize": "Rebuild differently",
                     "retire": "Switch off", "defer": "Decide later", "undecided": "Not yet decided"}
SEVERITY_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
IMPACT_LABEL = {"high": "Blocks the decision", "medium": "Changes the plan", "low": "Good to know"}
# Where an answer came from. An engineer answering in the chat is not the client's owner deciding;
# the report says which it was, because only one of them may settle a record.
ANSWER_KIND_LABEL = {"client-confirmed": "The named owner decided it",
                     "user-relayed": "Relayed by our engineer — the owner has still not confirmed",
                     "assumed-default": "Nobody answered; we applied the recorded default"}
EVIDENCE_TIER_LABEL = {"L0": "a claim or a slide", "L1": "an interview or a document",
                       "L2": "the source code", "L3": "a measurement on the live system"}
# Lakebridge Analyzer's own buckets. Using its wording means our §12 and the Analyzer output the
# client will eventually see are the same four words, not two competing scales.
COMPLEXITY_BUCKETS = ["Simple", "Medium", "Complex", "Very Complex"]
COMPLEXITY_ALIAS = {"simple": "Simple", "low": "Simple", "s": "Simple",
                    "medium": "Medium", "med": "Medium", "m": "Medium", "moderate": "Medium",
                    "complex": "Complex", "high": "Complex", "c": "Complex",
                    "very complex": "Very Complex", "very_complex": "Very Complex",
                    "very high": "Very Complex", "very_high": "Very Complex", "vc": "Very Complex"}
AXIS_C_LABEL = "The decision this report has to serve"
SUFF_LEGEND = ("✅ evidenced · ⚠️ partial — usable only within the limit stated in the row · "
               "❌ not evidenced — this conclusion cannot be drawn yet")

ID_PREFIX_LABEL = [
    ("FR-", "Functional requirement — something the platform must do"),
    ("DR-", "Data requirement — grain, lineage, retention, reconciliation"),
    ("SEC-", "Security requirement"),
    ("NFR-", "Service requirement — timing, availability, recovery"),
    ("SCOPE-", "Scope statement — what is in and out"),
    ("INT-", "Integration requirement — a system we must keep talking to"),
    ("BR-", "Business rule found in the current system"),
    ("FND-", "Finding — something we saw that carries risk"),
    ("OQ-", "Open question — someone has to answer it"),
    ("KPI-", "Success criterion — how we will know the migration worked"),
    ("obj-", "An object in the current system: table, procedure, job, report"),
]

# Only the terms that actually appear in the finished report are printed. A glossary of words the
# report never used is furniture.
GLOSSARY = {
    "medallion": "The three-step layout of data on Databricks: raw copy, then cleaned and conformed, then ready for reporting.",
    "bronze": "The raw landing layer — the source data copied in, unchanged, so anything can be rebuilt from it.",
    "silver": "The cleaned and conformed layer — de-duplicated, joined to reference data, business rules applied.",
    "gold": "The reporting layer — the tables and views the business actually reads.",
    "Unity Catalog": "The single place on Databricks that records who may see which table, column or file, and where each one came from.",
    "metric view": "A governed definition of a business measure, written once in Unity Catalog, so a dashboard, a SQL query and a spreadsheet all return the same number.",
    "Lakeflow Connect": "Databricks' managed connectors that pull data in from a source system without a hand-written loader.",
    "Lakeflow Declarative Pipelines": "Databricks' managed way of defining ETL, including data-quality expectations (formerly called Delta Live Tables).",
    "Lakeflow Jobs": "Databricks' scheduler — the replacement for a SQL Server Agent job or a cron chain.",
    "Lakehouse Federation": "Querying a source database directly from Databricks, read-only, without copying it first — useful to profile a source before committing to ingest it.",
    "AI/BI dashboard": "Databricks' built-in dashboard, which reads governed tables and metric views directly.",
    "Delta table": "The storage format Databricks uses; it supports updates, deletes and time travel, unlike a plain file.",
    "CDC": "Change data capture — reading only the rows that changed since last time, instead of re-reading everything.",
    "watermark": "A high-water mark (usually a timestamp) recorded after each load so the next load knows where to resume.",
    "service principal": "A named machine identity that a job runs as, instead of a shared login or a person's account.",
    "secret scope": "The vault a job reads a password from, so the password is never written into a file.",
    "transpile": "Machine translation of legacy SQL or ETL into Databricks code. The share that translates without hand-editing is the single biggest driver of migration effort.",
    "Lakebridge": "Databricks' free toolkit that inventories legacy code, scores each object's complexity, and converts it.",
    "SAT": "Security Analysis Tool — Databricks' free scan of an account and workspace against security best practice.",
    "PII": "Personal data — a name, a national ID, a phone number, an email — that carries legal obligations.",
    "backfill": "Loading history into the new platform, as opposed to today's data.",
    "reconciliation baseline": "The agreed set of numbers the old and the new system must both produce before anyone switches over.",
    "parallel run": "A period when old and new run side by side and their numbers are compared every day.",
    "locator": "A pointer — file and line, document page, interview timestamp — where a statement in this report can be checked in about five seconds.",
    "wave": "One deliverable batch of the migration: a set of objects that go live together, with their own prerequisites and exit test.",
    "pilot": "The first wave's first workload — deliberately business-visible, so the method is proven on something people recognise.",
    "orphan": "An object that nothing has read inside the usage window, and so is a candidate to switch off.",
}

# Default source → target mapping. A project overrides or extends it with
# registers/technology_map.jsonl; Databricks names follow databricks-builtin-map.md (2026 naming).
TECH_MAP = {
    "table":             ("Delta table in Unity Catalog", "Layer decided per object in §9; names stay <catalog> until agreed."),
    "view":              ("View, or a Unity Catalog metric view when it defines a measure", "Measures belong in a metric view, not copied into N gold tables."),
    "procedure":         ("Lakeflow Declarative Pipeline, or a SQL task in a Lakeflow Job", "Row-by-row logic (cursors) must be rewritten set-based, not translated."),
    "ssis_package":      ("Lakeflow Declarative Pipelines; ingestion parts to Lakeflow Connect", "Package-level variables become job parameters; embedded passwords become a secret scope."),
    "job":               ("Lakeflow Jobs", "Serial chains that have no real dependency are drawn as parallel branches in the target."),
    "report":            ("AI/BI dashboard over a Unity Catalog metric view", "Rules that live in the report definition move into the metric view, or the numbers stay inconsistent."),
    "external_source":   ("Lakeflow Connect where the connector exists; otherwise a watermarked incremental read", "Lakehouse Federation first, to profile the source before committing to ingest it."),
    "external_consumer": ("SQL warehouse endpoint with an explicit Unity Catalog grant", "Every consumer must be found before cut-over; each one is a re-point task."),
    "linked_server":     ("Lakehouse Federation foreign catalog", "Read-only; not a substitute for ingestion where the data is needed repeatedly."),
    "file_drop":         ("Auto Loader into the raw layer", "One ingestion path per source; two paths for the same data is a finding, not a design."),
}


def label(m, v, fallback=None):
    """Plain label for a register code. Unknown codes pass through — never silently blanked."""
    if v is None:
        return fallback if fallback is not None else ""
    return m.get(str(v), m.get(str(v).lower(), str(v)))


def complexity_bucket(v, warn=None):
    """Normalise a complexity value onto the four Lakebridge buckets."""
    if v in (None, ""):
        return None
    k = str(v).strip()
    if k in COMPLEXITY_BUCKETS:
        return k
    b = COMPLEXITY_ALIAS.get(k.lower())
    if not b and warn is not None:
        warn.add(k)
    return b or k


# ---------- loading ----------
def read_jsonl(p: Path):
    out = []
    if not p.exists():
        return out
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.stderr.write(f"warn: {p}:{i}: {e}\n")
    return out


def load_registers(root: Path, include_unreviewed: bool):
    names = ["requirements", "business_rules", "inventory", "inventory_tables", "inventory_pipelines",
             "inventory_reports", "dependency_edges", "findings", "open_questions", "rationalization",
             "success_criteria", "technology_map"]
    regs = {n: read_jsonl(root / "registers" / f"{n}.jsonl") for n in names}
    if include_unreviewed:
        for run in sorted((root / "runs").glob("*/")) if (root / "runs").exists() else []:
            for n in names:
                regs[n] += read_jsonl(run / f"{n}.jsonl")
    # merge legacy split inventories into one
    regs["inventory"] += regs.pop("inventory_tables") + regs.pop("inventory_pipelines") + regs.pop("inventory_reports")
    # de-dup by id (later wins)
    for n, recs in regs.items():
        seen = {}
        for r in recs:
            seen[r.get("id") or r.get("object_id") or json.dumps(r, sort_keys=True)] = r
        regs[n] = list(seen.values())
    if not include_unreviewed:
        for n in ("requirements", "business_rules", "inventory", "findings", "success_criteria"):
            regs[n] = [r for r in regs[n] if r.get("status") in REVIEWED]
    return regs


def locs(rec):
    ls = [e.get("locator") for e in rec.get("evidence", []) if e.get("locator")]
    if not ls and rec.get("source", {}).get("locator"):
        ls = [rec["source"]["locator"]]
    return "; ".join(ls) if ls else "NO LOCATOR"


def stem(text, limit=90):
    """First clause of a question, for routing lists where the full text lives elsewhere.
    Multi-part questions ('X? And who owns it?') cut at the first sentence end."""
    t = " ".join(str(text or "").split())
    for mark in ("? ", "; "):
        i = t.find(mark)
        if 0 < i <= limit:
            return t[: i + 1]
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def md_text(p: Path):
    return p.read_text(encoding="utf-8") if p.exists() else ""


def demote(md, by=1):
    """Splice a whole file under a report heading: drop its own title, push the rest down a level.
    Without this a '## …' inside sufficiency.md lands between Appendix C and Appendix D and reads as
    a section of the report."""
    md = re.sub(r"\A\s*#\s+[^\n]*\n+", "", md)
    return re.sub(r"(?m)^(#{1,5})(\s)", lambda m: "#" * min(len(m.group(1)) + by, 6) + m.group(2), md)


def decision_line(axis_c):
    """The one sentence §0 prints. intake.md's decision block often opens with the quote that
    motivated the decision; §1 keeps the whole block, §0 keeps only the decision."""
    t = " ".join(" ".join(l.strip().lstrip(">").strip() for l in axis_c.splitlines()).split())
    m = re.search(r"(This report is for\b.*)", t)
    t = m.group(1) if m else t
    return re.sub(r"\s*`?(inferred|stated|assumed)`?\s*[—-]\s*OQ-\d+\.?\s*$", "", t).strip()


def answered(oq, kind):
    return [q for q in oq if q.get("answer_kind") == kind]


def short_name(n, limit=26):
    """'MP_DWH.dbo.STG_POS_TXN' → 'STG_POS_TXN'. Diagram labels have no room for the full path, and
    Mermaid breaks on brackets and quotes inside one, so they go."""
    s = re.sub(r'["\[\]{}()|<>]', " ", str(n or "")).strip()
    s = " ".join((s.split(".")[-1] or s).split())
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-_") + "…"


# ---------- workbook ----------
HDR = PatternFill("solid", fgColor="1F3A5F")
HDR_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")


def sheet(wb, title, header, rows, widths=None, freeze=True):
    ws = wb.create_sheet(title[:31])
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font, c.alignment = HDR, HDR_FONT, WRAP
    for r in rows:
        ws.append(["" if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for v in r])
    for i, h in enumerate(header, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, 18)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = WRAP
    if freeze:
        ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    return ws


def tech_rows(regs):
    """Source kind → Databricks target. Register rows win over the built-in map; kinds actually
    present in the inventory come first, so the table describes this estate, not every estate."""
    override = {str(r.get("source_kind")): r for r in regs["technology_map"]}
    present = [k for k, _ in Counter(i.get("kind") for i in regs["inventory"]).most_common() if k]
    rows, seen = [], set()
    for k in present + [k for k in TECH_MAP if k not in present]:
        if k in seen:
            continue
        seen.add(k)
        o = override.get(k)
        tgt, note = TECH_MAP.get(k, ("— not mapped; the architect decides", ""))
        n = sum(1 for i in regs["inventory"] if i.get("kind") == k)
        rows.append([k, n, (o or {}).get("target", tgt), (o or {}).get("note", note), locs(o) if o else ""])
    return [r for r in rows if r[1] or r[0] in override]


def build_xlsx(regs, root, out, axis_c, suff_bad, cwarn):
    wb = Workbook()
    wb.remove(wb.active)
    req, rules, inv, edges, fnd, oq, rat, kpi = (regs[k] for k in
        ("requirements", "business_rules", "inventory", "dependency_edges", "findings",
         "open_questions", "rationalization", "success_criteria"))

    # Summary
    ws = wb.create_sheet("Summary")
    disp = Counter(r.get("disposition") or "undecided" for r in rat)
    rs = Counter(r.get("rule_status", "?") for r in rules)
    hi = [q for q in oq if q.get("impact_if_wrong") == "high" and q.get("status", "open") == "open"]
    lines = [["Project", root.name], [AXIS_C_LABEL, axis_c or "MISSING — fix intake.md"], [],
             ["Counts", ""], ["Requirements", len(req)], ["Business rules", len(rules)], ["Inventory objects", len(inv)],
             ["Findings", len(fnd)], ["Success criteria", len(kpi)],
             ["Open questions (open)", sum(1 for q in oq if q.get("status", "open") == "open")],
             ["  of which blocking (impact high)", len(hi)], [],
             ["Scope decision", ""]] + [[f"{d} — {DISPOSITION_LABEL[d]}", disp.get(d, 0)] for d in DISPOSITIONS + ["undecided"]] + [[],
             ["Business rules by certainty", ""]] + [[f"{k} — {label(RULE_STATUS_LABEL, k)}", v] for k, v in sorted(rs.items())] + [[],
             ["Evidence gaps (❌/⚠️)", len(suff_bad)]] + [["", " — ".join(c.strip() for c in l.strip().strip("|").split("|")[:2] if c.strip())] for l in suff_bad[:10]]
    for l in lines:
        ws.append(l)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 44, 110
    for c in ws["A"]:
        c.font = Font(bold=True)

    dflt = [q for q in oq if q.get("answer_kind") == "assumed-default"]
    sheet(wb, "Decisions", ["id", "state", "question", "why", "ask", "default", "answer",
                            "whose answer it is", "impact", "impact_if_wrong", "blocking", "evidence"],
          [[q.get("id"), "waiting on an answer" if q in hi else "running on our default",
            q.get("question"), q.get("why"), q.get("ask"), q.get("default"), q.get("answer"),
            label(ANSWER_KIND_LABEL, q.get("answer_kind"), ""),
            label(IMPACT_LABEL, q.get("impact_if_wrong")), q.get("impact_if_wrong"),
            ", ".join(q.get("blocking", [])), locs(q)]
           for q in sorted(hi + [q for q in dflt if q not in hi], key=lambda q: q.get("id", ""))],
          {"question": 60, "why": 50, "ask": 24, "default": 40, "answer": 40,
           "whose answer it is": 40, "impact": 22, "evidence": 40})

    sheet(wb, "Rationalization", ["object_id", "kind", "name", "disposition", "what that means", "wave", "used",
                                  "usage_window_days", "covers_month_end", "complexity", "complexity_source",
                                  "on_critical_path", "rule_status_max", "rule certainty", "owner_agreed",
                                  "blocking", "evidence", "notes"],
          [[r.get("object_id"), r.get("kind"), r.get("name"), r.get("disposition"),
            label(DISPOSITION_LABEL, r.get("disposition"), "Not yet decided"), r.get("wave"),
            *(r.get("criteria", {}).get(k) for k in ("used", "usage_window_days", "covers_month_end")),
            complexity_bucket(r.get("criteria", {}).get("complexity"), cwarn),
            *(r.get("criteria", {}).get(k) for k in ("complexity_source", "on_critical_path", "rule_status_max")),
            label(RULE_STATUS_LABEL, r.get("criteria", {}).get("rule_status_max")),
            r.get("criteria", {}).get("owner_agreed"),
            ", ".join(r.get("blocking", [])), locs(r), r.get("notes")] for r in rat],
          {"name": 36, "what that means": 24, "rule certainty": 38, "evidence": 40, "notes": 40})

    sheet(wb, "Findings", ["id", "severity", "category", "title", "impact", "detail", "requirements_raised",
                           "questions_raised", "evidence", "status", "review state"],
          [[f.get("id"), f.get("severity"), f.get("category"), f.get("title"), f.get("impact"), f.get("detail"),
            ", ".join(f.get("requirements_raised", [])), ", ".join(f.get("questions_raised", [])), locs(f),
            f.get("status"), label(STATUS_LABEL, f.get("status"))]
           for f in sorted(fnd, key=lambda f: SEV.get(f.get("severity"), 9))],
          {"title": 48, "impact": 44, "detail": 60, "evidence": 40, "review state": 22})

    sheet(wb, "Business Rules", ["id", "name", "rule_status", "certainty", "logic", "plain", "anchor",
                                 "config_driven", "in_spec", "requirements", "open_questions", "locator",
                                 "status", "review state"],
          [[r.get("id"), r.get("name"), r.get("rule_status"), label(RULE_STATUS_LABEL, r.get("rule_status")),
            r.get("logic"), r.get("plain"), (r.get("anchor") or {}).get("identifier"),
            r.get("config_driven"), r.get("in_spec"), ", ".join(r.get("requirements", [])),
            ", ".join(r.get("open_questions", [])), locs(r), r.get("status"), label(STATUS_LABEL, r.get("status"))]
           for r in rules],
          {"name": 36, "certainty": 38, "logic": 40, "plain": 50, "anchor": 30, "locator": 36, "review state": 22})

    sheet(wb, "Requirements", ["id", "type", "priority", "title", "statement", "domain", "inferred", "confidence",
                               "conflicts", "open_questions", "target_layer", "target_object", "owner", "evidence",
                               "status", "review state"],
          [[r.get("id"), r.get("type"), r.get("priority"), r.get("title"), r.get("statement"), r.get("domain"),
            r.get("inferred"), r.get("confidence"), "; ".join(f"{c.get('source_id')}@{c.get('locator')}: {c.get('note')}" for c in r.get("conflicts", [])),
            ", ".join(r.get("open_questions", [])), (r.get("target_mapping") or {}).get("layer"),
            (r.get("target_mapping") or {}).get("object"), r.get("owner"), locs(r), r.get("status"),
            label(STATUS_LABEL, r.get("status"))] for r in req],
          {"title": 44, "statement": 60, "conflicts": 44, "evidence": 40, "review state": 22})

    sheet(wb, "Success Criteria", ["id", "metric", "today", "target", "measured_by", "owner", "wave",
                                   "evidence", "status", "review state"],
          [[k.get("id"), k.get("metric"), k.get("today"), k.get("target"), k.get("measured_by"),
            k.get("owner"), k.get("wave"), locs(k), k.get("status"), label(STATUS_LABEL, k.get("status"))]
           for k in sorted(kpi, key=lambda k: k.get("id", ""))],
          {"metric": 46, "today": 26, "target": 26, "measured_by": 40, "owner": 26, "evidence": 34})

    sheet(wb, "Technology Map", ["source_kind", "objects in this estate", "Databricks target", "note", "evidence"],
          tech_rows(regs), {"source_kind": 22, "Databricks target": 56, "note": 70, "evidence": 30})

    sheet(wb, "Inventory", ["id", "kind", "name", "layer_guess", "row_estimate", "size_gb", "schedule", "avg_runtime_min",
                            "run_as", "readers", "writers", "reads", "writes", "consumers", "exec_count_90d", "last_read_at",
                            "last_write_at", "last_exec_at", "orphan", "pii_candidates", "complexity", "complexity_source",
                            "disposition", "what that means", "evidence", "status"],
          [[i.get("id"), i.get("kind"), i.get("name"), i.get("layer_guess"), i.get("row_estimate"), i.get("size_gb"),
            i.get("schedule"), i.get("avg_runtime_min"), i.get("run_as"), ", ".join(i.get("readers", [])), ", ".join(i.get("writers", [])),
            ", ".join(i.get("reads", [])), ", ".join(i.get("writes", [])), ", ".join(i.get("consumers", [])), i.get("exec_count_90d"),
            i.get("last_read_at"), i.get("last_write_at"), i.get("last_exec_at"), i.get("orphan"), ", ".join(i.get("pii_candidates", [])),
            complexity_bucket(i.get("complexity"), cwarn), i.get("complexity_source"), i.get("disposition"),
            label(DISPOSITION_LABEL, i.get("disposition"), ""), locs(i), i.get("status")] for i in inv],
          {"name": 36, "evidence": 36, "what that means": 22})

    # Answered questions stay on the tab. Dropping them loses the only record of what was decided,
    # by whom, and on whose authority — which is exactly what someone re-reads six months later.
    byp = defaultdict(list)
    for q in oq:
        byp[q.get("ask") or "unassigned"].append(q)
    rows = []
    for who, qs in sorted(byp.items()):
        for q in qs:
            draft = (f"Hi {who},\n\nWhile reviewing {locs(q)} we found: {q.get('why')}\n\nQuestion: {q.get('question')}\n"
                     f"If we hear nothing by <date>, we will assume: {q.get('default')}\n\nThanks")
            rows.append([who, q.get("id"), q.get("status", "open"), q.get("question"), q.get("why"),
                         q.get("default"), q.get("answer"), q.get("answer_kind"),
                         label(ANSWER_KIND_LABEL, q.get("answer_kind"), ""), q.get("answered_by"),
                         q.get("answered_at"), label(IMPACT_LABEL, q.get("impact_if_wrong")),
                         q.get("impact_if_wrong"), ", ".join(q.get("blocking", [])), locs(q),
                         "" if q.get("status") == "answered" else draft])
    sheet(wb, "Open Questions", ["ask", "id", "status", "question", "why", "default", "answer",
                                 "answer_kind", "whose answer it is", "answered_by", "answered_at",
                                 "impact", "impact_if_wrong", "blocking", "evidence", "email_draft"],
          rows, {"question": 56, "why": 46, "default": 36, "answer": 46, "whose answer it is": 40,
                 "impact": 22, "evidence": 36, "email_draft": 80})

    # Traceability: requirement -> rules -> objects -> questions
    rule_by_id = {r.get("id"): r for r in rules}
    trows = []
    for r in req:
        rls = r.get("related_rules", [])
        objs = sorted({(rule_by_id.get(x) or {}).get("anchor", {}).get("identifier") for x in rls} - {None})
        trows.append([r.get("id"), r.get("title"), ", ".join(rls), ", ".join(objs),
                      (r.get("target_mapping") or {}).get("object"), ", ".join(r.get("open_questions", [])), r.get("status")])
    sheet(wb, "Traceability", ["requirement", "title", "rules", "source_objects", "target_object", "open_questions", "status"],
          trows, {"title": 44, "rules": 30, "source_objects": 40, "target_object": 34})

    sheet(wb, "Dependencies", ["from", "to", "kind", "evidence"],
          [[e.get("from"), e.get("to"), e.get("kind"), locs(e)] for e in edges], {"from": 34, "to": 34, "evidence": 40})

    ws = wb.create_sheet("Sufficiency")
    ws.append(["Legend", SUFF_LEGEND])
    ws.append([])
    for l in md_text(root / "sufficiency.md").splitlines():
        if l.startswith("|") and not re.match(r"^\|\s*-", l):
            ws.append([c.strip() for c in l.strip("|").split("|")])
    for col in "ABCDE":
        ws.column_dimensions[col].width = 40

    sheet(wb, "Glossary", ["term", "what it means"],
          [[t, d] for t, d in sorted(GLOSSARY.items())] +
          [[f"{p}xx", d] for p, d in ID_PREFIX_LABEL] +
          [[c, d] for c, d in sorted(RULE_STATUS_LABEL.items())] +
          [[c, d] for c, d in sorted(STATUS_LABEL.items())],
          {"term": 30, "what it means": 120}, freeze=False)

    apr = []
    for run in sorted((root / "runs").glob("*/manifest.json")) if (root / "runs").exists() else []:
        m = json.loads(run.read_text(encoding="utf-8"))
        for a in m.get("approvals", []):
            apr.append([m.get("run_id"), a.get("what"), a.get("scope"), a.get("asked_at"),
                        a.get("granted_by"), a.get("granted_at"), a.get("expires")])
        for x in m.get("external_access", []):
            apr.append([m.get("run_id"), f"external access: {x.get('endpoint') or x}",
                        x.get("statement") if isinstance(x, dict) else "", "", "", "", ""])
    sheet(wb, "Approvals", ["run", "what was asked for", "scope granted", "asked_at", "granted_by",
                            "granted_at", "expires"], apr,
          {"what was asked for": 52, "scope granted": 46, "granted_by": 28})

    ws = wb.create_sheet("Sources")
    ws.append(["run", "source_id", "path", "sha256", "bytes"])
    for run in sorted((root / "runs").glob("*/manifest.json")) if (root / "runs").exists() else []:
        m = json.loads(run.read_text(encoding="utf-8"))
        for s in m.get("sources_read", []):
            ws.append([m.get("run_id"), s.get("source_id"), s.get("path"), s.get("sha256"), s.get("bytes")])
    ws.column_dimensions["C"].width, ws.column_dimensions["D"].width = 60, 66

    wb.save(out)


# ---------- diagram ----------
def mermaid(edges, inv, rat, limit=30):
    """A dependency picture a person can read: real names, grouped by layer, scoped to wave 1.

    The old version emitted `obj_0301 -->|triggers| obj_0101` for sixty edges — half a page that
    tells the reader nothing. Node ids are anonymous by design in the registers; a diagram is the
    one place they must not be."""
    if not edges:
        return []
    by_id = {i.get("id"): i for i in inv}
    name = lambda x: short_name((by_id.get(x) or {}).get("name") or x)
    wave1 = {r.get("object_id") for r in rat if r.get("wave") == 1}
    keep = wave1 or None
    if keep:
        es = [e for e in edges if e.get("from") in keep and e.get("to") in keep]
        scope = f"Wave 1 only — {len(keep)} objects. Full graph: workbook tab *Dependencies*."
    else:
        es = []
    if not es:  # no waves yet, or wave 1 has no internal edges — fall back to the busiest nodes
        deg = Counter()
        for e in edges:
            deg[e.get("from")] += 1
            deg[e.get("to")] += 1
        keep = {n for n, _ in deg.most_common(limit)}
        es = [e for e in edges if e.get("from") in keep and e.get("to") in keep]
        scope = f"The {len(keep)} most connected objects. Full graph: workbook tab *Dependencies*."
    es = es[:60]
    nodes = {n for e in es for n in (e.get("from"), e.get("to"))}
    nid = {n: f"n{i}" for i, n in enumerate(sorted(nodes), 1)}
    groups = defaultdict(list)
    for n in sorted(nodes):
        groups[(by_id.get(n) or {}).get("layer_guess") or (by_id.get(n) or {}).get("kind") or "other"].append(n)
    out = [f"\n_{scope}_\n", "\n```mermaid\ngraph LR\n"]
    for g, ns in sorted(groups.items()):
        out.append(f'  subgraph {re.sub(r"[^A-Za-z0-9_]", "_", str(g))}["{g}"]\n')
        out += [f'    {nid[n]}["{name(n)}"]\n' for n in ns]
        out.append("  end\n")
    out += [f"  {nid[e['from']]} -->|{e.get('kind')}| {nid[e['to']]}\n" for e in es]
    return out + ["```\n"]


# ---------- register check ----------
# Patterns that must not reach the business half of the report. Each is something a sponsor cannot
# look up: our own intake vocabulary, a JSON field name, a status code, a file name.
BANNED = [
    (r"\bAxis\s+[ABC]\b", "internal intake vocabulary — say what the decision is"),
    (r"\b(CODE-ONLY|DOC-ONLY|CONFIG-ONLY|CONFLICT|VERIFIED|UNRESOLVED|DEAD)\b", "raw rule_status code — use its plain label"),
    (r"\b(rule_status|complexity_source|owner_agreed|impact_if_wrong|dependency_edges|open_questions|rationalization|layer_guess|exec_count_90d)\b", "register field name"),
    (r"(?<![\w-])extracted(?![\w-])", "workflow state — say Draft"),
    (r"\bL[0-3]\b(?!\w)", "evidence-tier code — say where the evidence came from"),
    (r"\bcone\b", "in-house metaphor"),
    (r"\.jsonl\b", "register file name"),
]
BANNED_SUBJECT = re.compile(r"^\s*\|?\s*(OQ|FND|BR|FR|DR|NFR|SEC|INT|SCOPE|KPI)-\d+\b")


def check_register(md, strict):
    """Warn on internal vocabulary inside §0–§5. Text between '## 0.' and '## 6.' is the business
    half; everything after is the technical half and may use the codes."""
    body = md.split("\n")
    try:
        a = next(i for i, l in enumerate(body) if l.startswith("## 0."))
        b = next(i for i, l in enumerate(body) if l.startswith("## 6."))
    except StopIteration:
        return
    bad = []
    for n, l in enumerate(body[a:b], a + 1):
        for pat, why in BANNED:
            m = re.search(pat, l)
            if m:
                bad.append((n, m.group(0), why))
        if BANNED_SUBJECT.match(l):
            bad.append((n, l.strip()[:24], "an ID is the subject of the line — lead with the sentence, put the ID last"))
    for n, tok, why in bad[:40]:
        print(f"{'error' if strict else 'warning'}: report line {n}: '{tok}' — {why}", file=sys.stderr)
    if bad:
        print(f"{len(bad)} business-register violations in §0–§5. "
              f"Those sections are read by a sponsor who cannot look any of this up.", file=sys.stderr)
        if strict:
            sys.exit(1)


def glossary_used(md):
    used = [(t, d) for t, d in GLOSSARY.items() if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", md, re.I)]
    return sorted(used)


# ---------- report ----------
def build_md(regs, root, axis_c, suff_bad, author, cwarn):
    req, rules, inv, edges, fnd, oq, rat, kpi = (regs[k] for k in
        ("requirements", "business_rules", "inventory", "dependency_edges", "findings",
         "open_questions", "rationalization", "success_criteria"))
    A = lambda k: author.get(k, f"_Author section `{k}` not provided — pass --author-sections._\n")
    hi = [q for q in oq if q.get("impact_if_wrong") == "high" and q.get("status", "open") == "open"]
    defaulted, relayed = answered(oq, "assumed-default"), answered(oq, "user-relayed")
    dec = sum(1 for r in rat if r.get("disposition") in DISPOSITIONS and r.get("disposition") != "defer")
    blocked = sum(1 for r in rat if r.get("blocking"))

    md = [f"# {root.name} — Discovery & Assessment\n"]

    # §0 answers the question before it explains it. Everything below §0 is the defence of §0.
    md += ["\n## 0. In five lines\n\n", A("summary"), "\n"]
    md += ["| | |\n|---|---|\n",
           f"| Decision to be made | {decision_line(axis_c) or 'MISSING — fix intake.md'} |\n",
           f"| Scope settled so far | {dec} of {len(rat)} objects ({dec * 100 // max(len(rat), 1)}%) |\n",
           f"| Waiting on someone | {len(hi)} decisions nobody has answered; {blocked} objects blocked by one |\n",
           f"| Decisions taken on our default, unanswered | {len(defaulted)} (§2) |\n",
           f"| Conclusions the evidence will not carry yet | {len(suff_bad)} (§4) |\n",
           f"| Rules recovered from the current system | {len(rules)}, of which "
           f"{sum(1 for r in rules if r.get('rule_status') == 'VERIFIED')} confirmed by both code and document |\n"]

    md += ["\n## 1. Decision and recommendation\n\n", (axis_c or "> The decision this report serves is missing from intake.md") + "\n\n", A("decision")]

    md += ["\n## 2. Decisions required\n\nEach row needs one named person to answer it. "
           "Where nobody answers, we proceed on the default in the last column and record that we did.\n\n",
           "| Decision | Who answers | If nobody answers, we assume | Ref |\n|---|---|---|---|\n"]
    md += [f"| {q.get('question')} | {q.get('ask')} | {q.get('default')} | {q.get('id')} |\n" for q in hi] or ["| none open | | | |\n"]
    if defaulted:
        md += ["\n**Already running on our assumption.** Nobody answered these by the date, so the "
               "default below is what the rest of this report assumes. Overturning one changes the work "
               "named in the last column.\n\n",
               "| Question | What we assumed | Who can still overturn it | What changes if they do | Ref |\n|---|---|---|---|---|\n"]
        md += [f"| {q.get('question')} | {q.get('answer') or q.get('default')} | {q.get('ask')} | "
               f"{', '.join(q.get('blocking', [])) or '—'} | {q.get('id')} |\n" for q in defaulted]
    if relayed:
        md += [f"\n> {len(relayed)} of the answers behind this report came from our own engineer, not from "
               f"the named owner. They are good enough to plan on and not good enough to sign off; each one "
               f"is still open against its owner in the workbook.\n"]

    md += ["\n## 3. Scope — what we move, rebuild, switch off, or decide later\n\n"]
    if rat:
        und = len(rat) - dec
        md += [f"**{dec} of {len(rat)} objects decided ({dec * 100 // max(len(rat), 1)}%). "
               f"{und} undecided or held back; {blocked} waiting on an answer from §2.**\n\n"]
        by = defaultdict(Counter)
        for r in rat:
            by[r.get("kind", "?")][r.get("disposition") or "undecided"] += 1
        md += ["| What it is | " + " | ".join(DISPOSITION_LABEL[d] for d in DISPOSITIONS) + " | Not yet decided |\n|---|" + "---|" * 5 + "\n"]
        md += [f"| {k} | " + " | ".join(str(c.get(d, 0)) for d in DISPOSITIONS) + f" | {c.get('undecided', 0)} |\n" for k, c in by.items()]
        ret = [r for r in rat if r.get("disposition") == "retire"]
        agreed = sum(1 for r in ret if (r.get("criteria") or {}).get("owner_agreed"))
        md += [f"\n**Proposed to switch off: {len(ret)}.** {agreed} of them has an owner's agreement on record; "
               f"the rest are recommendations, not decisions.\n\n" if ret else "\n"]
        if ret:
            md += ["| Object | Owner has agreed | Where to check |\n|---|---|---|\n"]
            md += [f"| {r.get('name')} | {'yes' if (r.get('criteria') or {}).get('owner_agreed') else 'not yet'} | {locs(r)} |\n" for r in ret[:15]]
        confirmed_ids = {q.get("id") for q in answered(oq, "client-confirmed")}
        unbacked = [r for r in ret if (r.get("criteria") or {}).get("owner_agreed")
                    and not (set(r.get("blocking", [])) & confirmed_ids)]
        if unbacked:
            md += [f"\n> {len(unbacked)} of these are marked as agreed by an owner without a confirmation on "
                   f"record from the person named. Treat them as recommendations until there is one.\n"]
        manual = sum(1 for r in rat if (r.get("criteria") or {}).get("complexity_source") not in (None, "analyzer"))
        if manual:
            md += [f"\n> {manual} objects carry a complexity tier someone judged by eye, not one that was measured. "
                   f"Run the Lakebridge Analyzer over the full code export before anyone quotes an effort figure.\n"]
    else:
        md += ["_No scope decision has been recorded yet._\n"]

    md += ["\n## 4. What the evidence does not yet support\n\n",
           "This section is here, and not in an appendix, because it is the part that decides what may be "
           "quoted out of this report.\n\n", SUFF_LEGEND + "\n\n"]
    if suff_bad:
        hdr = next((l for l in md_text(root / "sufficiency.md").splitlines() if l.startswith("|") and "Conclusion" in l), None)
        if hdr:
            md += [hdr + "\n", "|" + "---|" * (hdr.count("|") - 1) + "\n"]
        md += [l + "\n" for l in suff_bad]
    else:
        md += ["_Nothing is marked ⚠️ or ❌ in the sufficiency check — confirm that is really true._\n"]

    md += ["\n## 5. How we will know it worked\n\n",
           "Agreed before the build starts, measured the same way on both platforms. "
           "A criterion with no owner and no measurement is a wish.\n\n"]
    if kpi:
        md += ["| What we measure | Today | Target | Measured how | Who signs it off | Wave | Ref |\n|---|---|---|---|---|---|---|\n"]
        md += [f"| {k.get('metric')} | {k.get('today') or '— not measured'} | {k.get('target') or '— not set'} | "
               f"{k.get('measured_by') or '— not defined'} | {k.get('owner') or '— unassigned'} | {k.get('wave') or '—'} | {k.get('id')} |\n"
               for k in sorted(kpi, key=lambda k: k.get("id", ""))]
    else:
        md += ["_No success criteria agreed yet. Until they exist, nobody can say afterwards whether the "
               "migration succeeded. Databricks' own method treats these as an output of assessment, not of delivery._\n"]
    md += [A("success") if "success" in author else ""]

    md += ["\n---\n\n_Sections 6 onward are the technical record behind the five above. They use the register "
           "codes; Appendix A and B explain every one of them._\n"]

    md += ["\n## 6. Key findings\n\n| Finding | Severity | Impact | Evidence | Ref |\n|---|---|---|---|---|\n"]
    md += [f"| {f.get('title')} | {label(SEVERITY_LABEL, f.get('severity'))} | {f.get('impact', '')} | {locs(f)} | {f.get('id')} |\n"
           for f in sorted(fnd, key=lambda f: SEV.get(f.get("severity"), 9))[:10]]

    dist = Counter(r.get("rule_status", "?") for r in rules)
    md += ["\n## 7. Business rules at risk\n\nHow certain we are of each rule we recovered:\n\n",
           "| Certainty | Code | Rules |\n|---|---|---|\n"]
    md += [f"| {label(RULE_STATUS_LABEL, k)} | `{k}` | {v} |\n" for k, v in sorted(dist.items(), key=lambda kv: -kv[1])]
    md += ["\n| Rule | Certainty | Logic in the current system | Who confirms | Ref |\n|---|---|---|---|---|\n"]
    md += [f"| {r.get('name')} | {label(RULE_STATUS_LABEL, r.get('rule_status'))} | `{r.get('logic')}` | "
           f"{', '.join(r.get('open_questions', [])) or '—'} | {r.get('id')} |\n"
           for r in rules if r.get("rule_status") in ("CONFLICT", "CODE-ONLY", "CONFIG-ONLY")][:25]

    c = Counter((r.get("type"), r.get("status")) for r in req)
    md += ["\n## 8. Requirements\n\n| Type | Checked | Signed off by owner | Deferred | Draft |\n|---|---|---|---|---|\n"]
    md += [f"| {t} | " + " | ".join(str(c.get((t, s), 0)) for s in ("reviewed", "confirmed", "deferred", "extracted")) + " |\n"
           for t in ("functional", "data", "security", "nonfunctional", "scope", "integration")]
    inf = [r for r in req if r.get("inferred")]
    conf = [r for r in req if r.get("conflicts")]
    md += [f"\n{len(req)} requirements · {len(inf)} inferred by us and awaiting the client's confirmation · "
           f"{len(conf)} where two sources disagree.\n"]
    md += [f"- {r.get('title')} → confirm via {', '.join(r.get('open_questions', [])) or 'no question raised yet'} ({r.get('id')})\n" for r in inf[:10]]

    md += ["\n## 9. Target architecture outline\n\n", A("architecture")]
    md += mermaid(edges, inv, rat)

    md += ["\n## 10. Platform foundation — governance and landing zone\n\n",
           "The decisions that have to be made once, before wave 1, and are expensive to change after: "
           "workspace and catalog layout, identity and groups, network and storage, secrets, CI/CD, "
           "monitoring and cost controls.\n\n", A("governance")]

    md += ["\n## 11. Source → target technology mapping\n\n",
           "What each kind of object in the current system becomes on Databricks. This is the shape of the "
           "work, not an estimate of it.\n\n",
           "| In the current system | Count | On Databricks | Note |\n|---|---|---|---|\n"]
    md += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |\n" for r in tech_rows(regs)]

    md += ["\n## 12. Waves, pilot, estimate drivers\n\n"]
    waves = defaultdict(list)
    for r in rat:
        if r.get("wave") is not None:
            waves[r["wave"]].append(r.get("name"))
    md += [f"- Wave {w}: {len(v)} objects\n" for w, v in sorted(waves.items())] or ["- No waves assigned yet.\n"]
    comp = Counter(complexity_bucket(i.get("complexity"), cwarn) for i in inv if i.get("complexity"))
    src = Counter(i.get("complexity_source") or "unstated" for i in inv if i.get("complexity"))
    if comp:
        md += ["\n| Complexity | Objects |\n|---|---|\n"]
        md += [f"| {b} | {comp.get(b, 0)} |\n" for b in COMPLEXITY_BUCKETS if comp.get(b)]
        md += [f"| {b} | {n} |\n" for b, n in comp.items() if b not in COMPLEXITY_BUCKETS and b]
        md += [f"\nScored by: " + ", ".join(f"{k} ({v})" for k, v in src.items()) +
               ". Only `analyzer` is a measurement; anything else is triage and must be labelled as such.\n"]
    else:
        md += ["\nComplexity: not assessed. No Lakebridge Analyzer output exists, so no object carries a "
               "Simple / Medium / Complex / Very Complex score and no effort figure can be derived from this report.\n"]
    md += [A("drivers")]

    md += ["\n## 13. Business case inputs\n\n",
           "What is needed to turn this assessment into a cost comparison, and what is missing today. "
           "No saving is asserted anywhere in this report.\n\n", A("business_case")]

    md += ["\n## 14. Risks and cost flags\n\n", A("risks")]

    # §2 already prints the high-impact questions in full. Repeating them here doubled the longest
    # section of the report, so this is a routing list: who to ask, what about, where the full text
    # lives (§2, or the workbook tab *Open Questions*, which carries the email draft).
    md += ["\n## 15. Open questions by person\n\nRouting list. Full text: §2 for the blocking ones, "
           "workbook tab *Open Questions* for all, with a ready email draft per row.\n"]
    hi_ids = {q.get("id") for q in hi}
    byp = defaultdict(list)
    for q in oq:
        if q.get("status", "open") == "open":
            byp[q.get("ask") or "unassigned"].append(q)
    for p, qs in sorted(byp.items()):
        md += [f"\n**{p}** — {len(qs)}\n"]
        for q in qs:
            md += [f"- {stem(q.get('question'))} — full text §2 ({q.get('id')})\n" if q.get("id") in hi_ids
                   else f"- {stem(q.get('question'))} [{locs(q)}] ({q.get('id')})\n"]

    body = "".join(md)

    gl = glossary_used(body)
    app = ["\n## Appendix A — Glossary\n\nEvery term in this report that is Databricks' vocabulary "
           "rather than yours.\n\n| Term | What it means |\n|---|---|\n"]
    app += [f"| {t} | {d} |\n" for t, d in gl] or ["| — | none used |\n"]

    app += ["\n## Appendix B — How to read this report\n\n**Evidence marks.** " + SUFF_LEGEND + "\n\n",
            "**Reference codes.** Every claim carries a code so you can find the record behind it in the workbook.\n\n",
            "| Code | What it is |\n|---|---|\n"]
    app += [f"| `{p}xx` | {d} |\n" for p, d in ID_PREFIX_LABEL]
    app += ["\n**How certain a business rule is.**\n\n| Code | What it means |\n|---|---|\n"]
    app += [f"| `{k}` | {v} |\n" for k, v in RULE_STATUS_LABEL.items()]
    app += ["\n**How far a record has been reviewed.**\n\n| Code | What it means |\n|---|---|\n"]
    app += [f"| `{k}` | {v} |\n" for k, v in STATUS_LABEL.items() if k in ("extracted", "reviewed", "confirmed", "deferred", "rejected")]
    app += ["\n**Where an answer came from.**\n\n| Code | What it means |\n|---|---|\n"]
    app += [f"| `{k}` | {v} |\n" for k, v in ANSWER_KIND_LABEL.items()]
    app += ["\n**Where a piece of evidence came from.**\n\n| Code | Means the statement rests on |\n|---|---|\n"]
    app += [f"| `{k}` | {v} |\n" for k, v in EVIDENCE_TIER_LABEL.items()]
    app += ["\n**What we propose to do with each object.**\n\n| Code | What it means |\n|---|---|\n"]
    app += [f"| `{k}` | {v} |\n" for k, v in DISPOSITION_LABEL.items()]

    app += ["\n## Appendix C — Evidence sufficiency\n\n", demote(md_text(root / "sufficiency.md")) or "_missing_\n"]
    pend = sum(1 for f in (root / "runs").glob("*/*.jsonl") for r in read_jsonl(f) if r.get("status") == "extracted") if (root / "runs").exists() else 0
    app += [f"\n## Appendix D — Sources\n\nRecords still in `extracted` (Draft) state and therefore excluded "
            f"from this report unless `--include-unreviewed` was used: {pend}. Full list: workbook tab *Sources*.\n"]
    return body + "".join(app)


def parse_author_sections(p: Path):
    """Markdown with one '## <name>' heading per author section; see AUTHOR_CAPS for the list."""
    if not p or not p.exists():
        return {}
    out, key, buf = {}, None, []
    pat = re.compile(r"^##\s+(" + "|".join(AUTHOR_KEYS) + r")\s*$", re.I)
    for l in p.read_text(encoding="utf-8").splitlines():
        m = pat.match(l.strip())
        if m:
            if key:
                out[key] = "\n".join(buf).strip() + "\n"
            key, buf = m.group(1).lower(), []
        elif key:
            buf.append(l)
    if key:
        out[key] = "\n".join(buf).strip() + "\n"
    for k, cap in AUTHOR_CAPS.items():
        n = len(out.get(k, "").split())
        if n > cap:
            print(f"warning: author section '{k}' is {n} words, over the {cap}-word budget. "
                  f"Prose past the budget is usually description, not decision — cut it or move it "
                  f"into a record with a locator.", file=sys.stderr)
    missing = [k for k in AUTHOR_KEYS if k not in out]
    if missing:
        print(f"warning: author sections not provided: {', '.join(missing)}. "
              f"They render as a visible placeholder rather than quietly disappearing.", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir")
    ap.add_argument("--out-dir", default=None, help="default: parent of project dir")
    ap.add_argument("--include-unreviewed", action="store_true")
    ap.add_argument("--author-sections", default=None)
    ap.add_argument("--no-docx", action="store_true")
    ap.add_argument("--strict-register", action="store_true",
                    help="fail instead of warning when §0–§5 use internal vocabulary")
    a = ap.parse_args()
    root = Path(a.project_dir).resolve()
    out = Path(a.out_dir).resolve() if a.out_dir else root.parent
    out.mkdir(parents=True, exist_ok=True)

    regs = load_registers(root, a.include_unreviewed)
    intake = md_text(root / "intake.md")
    axis_c = "\n".join(l for l in intake.splitlines() if l.strip().startswith(">"))
    suff_bad = [l for l in md_text(root / "sufficiency.md").splitlines() if "❌" in l or "⚠️" in l]
    author = parse_author_sections(Path(a.author_sections)) if a.author_sections else {}
    cwarn = set()

    xlsx = out / f"discovery-{root.name}.xlsx"
    build_xlsx(regs, root, xlsx, axis_c, suff_bad, cwarn)
    md_path = out / "assessment-report.md"
    report = build_md(regs, root, axis_c, suff_bad, author, cwarn)
    md_path.write_text(report, encoding="utf-8")
    if cwarn:
        print(f"warning: complexity values not on the Lakebridge scale "
              f"({' / '.join(COMPLEXITY_BUCKETS)}): {', '.join(sorted(cwarn))}", file=sys.stderr)
    check_register(report, a.strict_register)
    print(f"wrote {xlsx}\nwrote {md_path}")
    if not a.no_docx and shutil.which("pandoc"):
        docx = out / "assessment-report.docx"
        r = subprocess.run(["pandoc", str(md_path), "-o", str(docx)], capture_output=True, text=True)
        print(f"wrote {docx}" if r.returncode == 0 else f"pandoc failed: {r.stderr.strip()}")
    elif not a.no_docx:
        print("pandoc not found — .docx skipped")


if __name__ == "__main__":
    main()
