#!/usr/bin/env python3
"""Generate the human-facing deliverables from discovery registers.

  python3 build_deliverables.py <discovery/project dir> [--out-dir <dir>] [--include-unreviewed]
                                [--author-sections <file.md>] [--no-docx]

Reads   <project>/registers/*.jsonl (or, with --include-unreviewed, also runs/*/ *.jsonl),
        <project>/intake.md, <project>/sufficiency.md
Writes  <out-dir>/discovery-<project>.xlsx      one workbook, tabs in reading order
        <out-dir>/assessment-report.md          generated; author sections merged from --author-sections
        <out-dir>/assessment-report.docx        via pandoc when available (skip with --no-docx)

Stdlib + openpyxl. Never invents: every number is followed by its locators; unreviewed records
are excluded unless asked for; placeholders like <catalog> are left visible.
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
# Word budgets for the five hand-written sections. The registers cap excerpts and details; without
# a cap here the prose grew to ~1,900 words and pushed the report past the twelve pages the skill
# argues for. Over budget is a warning, not an error — the author decides.
AUTHOR_CAPS = {"decision": 400, "architecture": 500, "roadmap": 400, "drivers": 300, "risks": 400}


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
             "inventory_reports", "dependency_edges", "findings", "open_questions", "rationalization", "readiness"]
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
            seen[r.get("id") or r.get("object_id") or r.get("dimension") or json.dumps(r, sort_keys=True)] = r
        regs[n] = list(seen.values())
    if not include_unreviewed:
        for n in ("requirements", "business_rules", "inventory", "findings", "readiness"):
            regs[n] = [r for r in regs[n] if r.get("status") in REVIEWED]
    return regs


def evidence_kind(rec):
    """The strongest evidence kind a record carries: reproduced > stated > inferred."""
    ks = {e.get("kind") for e in rec.get("evidence", [])}
    return next((k for k in ("reproduced", "stated", "inferred", "external") if k in ks), "none")


def finding_order(f):
    """Carried findings first — what a faithful migration would ship — then by severity."""
    return (0 if f.get("migration_disposition") == "carried" else 1, SEV.get(f.get("severity"), 9))


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


def build_xlsx(regs, root, out, axis_c, suff_bad):
    wb = Workbook()
    wb.remove(wb.active)
    req, rules, inv, edges, fnd, oq, rat = (regs[k] for k in
        ("requirements", "business_rules", "inventory", "dependency_edges", "findings", "open_questions", "rationalization"))

    # Summary
    ws = wb.create_sheet("Summary")
    disp = Counter(r.get("disposition") or "undecided" for r in rat)
    rs = Counter(r.get("rule_status", "?") for r in rules)
    hi = [q for q in oq if q.get("impact_if_wrong") == "high" and q.get("status", "open") == "open"]
    lines = [["Project", root.name], ["Decision (Axis C)", axis_c or "MISSING — fix intake.md"], [],
             ["Counts", ""], ["Requirements", len(req)], ["Business rules", len(rules)], ["Inventory objects", len(inv)],
             ["Findings", len(fnd)], ["Readiness (lowest scored of 5)", min((x for x in (readiness_score(r) for r in regs["readiness"]) if x), default="not scored")], ["Open questions (open)", sum(1 for q in oq if q.get("status", "open") == "open")],
             ["  of which blocking (impact high)", len(hi)], [],
             ["Rationalization", ""]] + [[d, disp.get(d, 0)] for d in DISPOSITIONS + ["undecided"]] + [[],
             ["rule_status", ""]] + [[k, v] for k, v in sorted(rs.items())] + [[],
             ["Evidence gaps (❌/⚠️)", len(suff_bad)]] + [["", " — ".join(c.strip() for c in l.strip().strip("|").split("|")[:2] if c.strip())] for l in suff_bad[:10]]
    for l in lines:
        ws.append(l)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 110
    for c in ws["A"]:
        c.font = Font(bold=True)

    rd = {r.get("dimension"): r for r in regs["readiness"]}
    sheet(wb, "Readiness", ["dimension", "score", "counted", "basis", "rationale", "needs", "evidence", "status"],
          [[k, (rd.get(k) or {}).get("score"), readiness_score(rd.get(k)) is not None, (rd.get(k) or {}).get("basis"),
            (rd.get(k) or {}).get("rationale"), (rd.get(k) or {}).get("needs"), locs(rd[k]) if k in rd else None,
            (rd.get(k) or {}).get("status")] for k, _ in READINESS],
          {"rationale": 60, "needs": 40, "evidence": 40})

    sheet(wb, "Decisions", ["id", "question", "why", "ask", "default", "impact_if_wrong", "blocking", "evidence"],
          [[q.get("id"), q.get("question"), q.get("why"), q.get("ask"), q.get("default"), q.get("impact_if_wrong"),
            ", ".join(q.get("blocking", [])), locs(q)] for q in sorted(hi, key=lambda q: q.get("id", ""))],
          {"question": 60, "why": 50, "ask": 24, "default": 40, "evidence": 40})

    sheet(wb, "Rationalization", ["object_id", "kind", "name", "disposition", "wave", "used", "usage_window_days",
                                  "covers_month_end", "complexity", "complexity_source", "on_critical_path",
                                  "rule_status_max", "owner_agreed", "target_component", "blocking", "evidence", "notes"],
          [[r.get("object_id"), r.get("kind"), r.get("name"), r.get("disposition"), r.get("wave"),
            *(r.get("criteria", {}).get(k) for k in ("used", "usage_window_days", "covers_month_end", "complexity",
                                                       "complexity_source", "on_critical_path", "rule_status_max", "owner_agreed")),
            r.get("target_component"), ", ".join(r.get("blocking", [])), locs(r), r.get("notes")] for r in rat],
          {"name": 36, "evidence": 40, "notes": 40})

    sheet(wb, "Findings", ["id", "severity", "category", "layer", "title", "impact", "detail", "when migrated",
                           "evidence kind", "requirements_raised", "questions_raised", "evidence", "status"],
          [[f.get("id"), f.get("severity"), f.get("category"), f.get("layer"), f.get("title"), f.get("impact"),
            f.get("detail"), f.get("migration_disposition") or "NOT SET", evidence_kind(f),
            ", ".join(f.get("requirements_raised", [])), ", ".join(f.get("questions_raised", [])), locs(f), f.get("status")]
           for f in sorted(fnd, key=finding_order)],
          {"title": 48, "impact": 44, "detail": 60, "evidence": 40})

    sheet(wb, "Business Rules", ["id", "name", "rule_status", "logic", "plain", "anchor", "config_driven", "in_spec",
                                 "requirements", "open_questions", "locator", "status"],
          [[r.get("id"), r.get("name"), r.get("rule_status"), r.get("logic"), r.get("plain"),
            (r.get("anchor") or {}).get("identifier"), r.get("config_driven"), r.get("in_spec"),
            ", ".join(r.get("requirements", [])), ", ".join(r.get("open_questions", [])), locs(r), r.get("status")] for r in rules],
          {"name": 36, "logic": 40, "plain": 50, "anchor": 30, "locator": 36})

    sheet(wb, "Requirements", ["id", "type", "priority", "title", "statement", "domain", "inferred", "confidence",
                               "conflicts", "open_questions", "target_layer", "target_object", "owner", "evidence", "status"],
          [[r.get("id"), r.get("type"), r.get("priority"), r.get("title"), r.get("statement"), r.get("domain"),
            r.get("inferred"), r.get("confidence"), "; ".join(f"{c.get('source_id')}@{c.get('locator')}: {c.get('note')}" for c in r.get("conflicts", [])),
            ", ".join(r.get("open_questions", [])), (r.get("target_mapping") or {}).get("layer"),
            (r.get("target_mapping") or {}).get("object"), r.get("owner"), locs(r), r.get("status")] for r in req],
          {"title": 44, "statement": 60, "conflicts": 44, "evidence": 40})

    sheet(wb, "Inventory", ["id", "kind", "name", "owner", "layer_guess", "row_estimate", "size_gb", "schedule", "avg_runtime_min",
                            "run_as", "readers", "writers", "reads", "writes", "consumers", "exec_count_90d", "last_read_at",
                            "last_write_at", "last_exec_at", "orphan", "pii_candidates", "holds_pii", "erasure_reaches", "complexity", "complexity_source",
                            "disposition", "evidence", "status"],
          [[i.get("id"), i.get("kind"), i.get("name"), i.get("owner"), i.get("layer_guess"), i.get("row_estimate"), i.get("size_gb"),
            i.get("schedule"), i.get("avg_runtime_min"), i.get("run_as"), ", ".join(i.get("readers", [])), ", ".join(i.get("writers", [])),
            ", ".join(i.get("reads", [])), ", ".join(i.get("writes", [])), ", ".join(i.get("consumers", [])), i.get("exec_count_90d"),
            i.get("last_read_at"), i.get("last_write_at"), i.get("last_exec_at"), i.get("orphan"), ", ".join(i.get("pii_candidates", [])), i.get("holds_pii"), i.get("erasure_reaches"),
            i.get("complexity"), i.get("complexity_source"), i.get("disposition"), locs(i), i.get("status")] for i in inv],
          {"name": 36, "evidence": 36})

    byp = defaultdict(list)
    for q in oq:
        if q.get("status", "open") == "open":
            byp[q.get("ask") or "unassigned"].append(q)
    rows = []
    for p, qs in sorted(byp.items()):
        for q in qs:
            draft = (f"Hi {p},\n\nWhile reviewing {locs(q)} we found: {q.get('why')}\n\nQuestion: {q.get('question')}\n"
                     f"If we hear nothing by <date>, we will assume: {q.get('default')}\n\nThanks")
            rows.append([p, q.get("id"), q.get("question"), q.get("why"), q.get("default"), q.get("impact_if_wrong"),
                         ", ".join(q.get("blocking", [])), locs(q), draft])
    sheet(wb, "Open Questions", ["ask", "id", "question", "why", "default", "impact_if_wrong", "blocking", "evidence", "email_draft"],
          rows, {"question": 56, "why": 46, "default": 36, "evidence": 36, "email_draft": 80})

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
    for l in md_text(root / "sufficiency.md").splitlines():
        if l.startswith("|") and not re.match(r"^\|\s*-", l):
            ws.append([c.strip() for c in l.strip("|").split("|")])
    for col in "ABCDE":
        ws.column_dimensions[col].width = 40

    ws = wb.create_sheet("Sources")
    ws.append(["run", "source_id", "path", "sha256", "bytes"])
    for run in sorted((root / "runs").glob("*/manifest.json")) if (root / "runs").exists() else []:
        m = json.loads(run.read_text(encoding="utf-8"))
        for s in m.get("sources_read", []):
            ws.append([m.get("run_id"), s.get("source_id"), s.get("path"), s.get("sha256"), s.get("bytes")])
    ws.column_dimensions["C"].width, ws.column_dimensions["D"].width = 60, 66

    wb.save(out)


# ---------- report ----------
# The report follows the delivery template: Part A (discovery, 1–5) describes what is there and is
# generated tables only; Part B (assessment, 6–12) is what to do about it. A section with nothing
# behind it prints one sentence — what it needs and what skipping it risks — never filler prose.
STORE_KINDS = {"table", "view", "file_store", "queue", "log", "cache", "object_store", "export"}
READINESS = [("data", "Data"), ("logic", "Logic / code"), ("governance", "Governance & PII"),
             ("security", "Security"), ("operations", "Operations")]


def readiness_score(r):
    """A dimension's 1–5 score, or None when the rules refuse it: no locator, no score; Security is
    scored only from a SAT run or workspace evidence, because reading code cannot see the posture."""
    s = (r or {}).get("score")
    if not isinstance(s, int) or not 1 <= s <= 5 or locs(r) == "NO LOCATOR":
        return None
    if r.get("dimension") == "security" and r.get("basis") not in ("sat", "workspace"):
        return None
    return s


def gap(needs, risk):
    return f"_Insufficient evidence — needs {needs}; risk if skipped: {risk}._\n"


def cell(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    return "—" if v in (None, "", []) else " ".join(str(v).split()).replace("|", "\\|")


def table(header, rows, cap=None, tab=None):
    if not rows:
        return []
    out = ["| " + " | ".join(header) + " |\n", "|" + "---|" * len(header) + "\n"]
    out += ["| " + " | ".join(cell(v) for v in r) + " |\n" for r in rows[:cap]]
    if cap and len(rows) > cap:
        out += [f"\n{len(rows) - cap} more — workbook tab *{tab}*.\n"]
    return out


def volume(i):
    parts = [f"{i['row_estimate']:,} rows" if isinstance(i.get("row_estimate"), int) else None,
             f"{i['size_gb']} GB" if i.get("size_gb") is not None else None,
             f"{i['exec_count_90d']} runs/90d" if i.get("exec_count_90d") is not None else None,
             f"{i['avg_runtime_min']} min/run" if i.get("avg_runtime_min") is not None else None]
    return ", ".join(p for p in parts if p)


def build_md(regs, root, axis_c, suff_bad, author, built_with=None, intake=""):
    req, rules, inv, edges, fnd, oq, rat = (regs[k] for k in
        ("requirements", "business_rules", "inventory", "dependency_edges", "findings", "open_questions", "rationalization"))
    A = lambda k: author.get(k, f"_Author section `{k}` not provided — pass --author-sections._\n")
    ev = lambda r: f"{evidence_kind(r)}: {locs(r)}"
    md = [f"# {root.name} — Discovery & Assessment\n"]
    # What the assessment was built on, so a reader weeks later can tell which
    # skills and CLI shaped it — the agent passes what its session knows.
    if built_with:
        md += [f"\n> Built with: {built_with}\n"]
    hi = [q for q in oq if q.get("impact_if_wrong") == "high" and q.get("status", "open") == "open"]

    # ---------- 1 ----------
    md += ["\n# Part A — Discovery\n", "\n## 1. Executive summary\n\n", (axis_c or "> Axis C missing in intake.md") + "\n\n"]
    rd = {r.get("dimension"): r for r in regs["readiness"]}
    scores = {k: readiness_score(rd.get(k)) for k, _ in READINESS}
    got = [s for s in scores.values() if s]
    unscored = len(READINESS) - len(got)
    if not got:
        md += ["**Readiness: not scored** — no dimension has evidence behind a score yet.\n\n"]
    elif unscored:
        md += [f"**Readiness: at most {min(got)} / 5** — the lowest scored dimension; {unscored} of "
               f"{len(READINESS)} are not scored yet and any of them can pull it lower.\n\n"]
    else:
        md += [f"**Readiness: {min(got)} / 5** — the lowest dimension; an estate is as ready as its weakest part.\n\n"]
    rows = []
    for k, label in READINESS:
        r = rd.get(k)
        if scores[k]:
            rows.append([label, f"{scores[k]} / 5", r.get("rationale"), locs(r)])
        else:
            need = (r or {}).get("needs") or "evidence behind a score"
            if k == "security" and (r or {}).get("basis") not in ("sat", "workspace"):
                need = "a SAT run or workspace evidence — reading code cannot score the posture"
            rows.append([label, "not scored", f"needs {need}", locs(r) if r else None])
    md += table(["Dimension", "Score", "Basis", "Evidence"], rows)

    md += ["\n### Top 5 risks\n\n"]
    top = sorted((f for f in fnd if f.get("severity") in ("critical", "high")), key=finding_order)[:5]
    md += table(["#", "Severity", "Risk", "When migrated", "Evidence"],
                [[f.get("id"), f.get("severity"), f.get("title"), f.get("migration_disposition") or "NOT SET", ev(f)] for f in top]) \
        or ([gap("findings from code or documents", "the recommendation rests on no known risk")] if not fnd
            else ["No critical or high finding reviewed.\n"])
    md += ["\n### Recommendation\n\n", A("decision"),
           f"\n{len(hi)} open decision(s) block this — §12.\n",
           "\n### What the evidence does not yet support\n\n"]
    if suff_bad:
        hdr = next((l for l in md_text(root / "sufficiency.md").splitlines() if l.startswith("|") and "Conclusion" in l), None)
        if hdr:
            md += [hdr + "\n", "|" + "---|" * (hdr.count("|") - 1) + "\n"]
        md += [l + "\n" for l in suff_bad]
    else:
        md += ["_no ❌/⚠️ rows in sufficiency.md — confirm that is true._\n"]

    # ---------- Part A ----------
    md += ["\n## 2. Business context & target-state requirements\n\n"]
    axis_a = next((l for l in intake.splitlines() if l.startswith("## Axis A")), None)
    if axis_a:
        md += [axis_a.lstrip("# ") + "\n\n"]
    if req:
        c = Counter((r.get("type"), r.get("status")) for r in req)
        md += ["| Type | reviewed | confirmed | deferred | extracted |\n|---|---|---|---|---|\n"]
        md += [f"| {t} | " + " | ".join(str(c.get((t, s), 0)) for s in ("reviewed", "confirmed", "deferred", "extracted")) + " |\n"
               for t in ("functional", "data", "security", "nonfunctional", "scope", "integration")]
        inf = [r for r in req if r.get("inferred")]
        md += [f"\n{len(req)} requirements · {len(inf)} inferred, awaiting confirmation (§12) · "
               f"{sum(1 for r in req if r.get('conflicts'))} carry a source conflict.\n\n"]
        # NFRs, SLAs, residency and scope live in these types; functional ones are the use cases.
        md += table(["Id", "Type", "Requirement", "Status", "Evidence"],
                    [[r.get("id"), r.get("type"), r.get("title"), r.get("status"), ev(r)]
                     for r in sorted(req, key=lambda r: (r.get("type") == "functional", r.get("id", "")))], 25, "Requirements")
    else:
        md += [gap("documents, transcripts or tickets read by requirements-extraction",
                   "the target is designed against assumed use cases, SLAs and residency")]

    md += ["\n## 3. Data landscape & current-state architecture\n\n"]
    stores = [i for i in inv if i.get("kind") in STORE_KINDS]
    if inv:
        by = defaultdict(list)
        for i in inv:
            by[i.get("kind") or "?"].append(i)
        md += table(["Kind", "Objects", "Holds PII", "PII not classified"],
                    [[k, len(v), sum(1 for i in v if i.get("holds_pii")), sum(1 for i in v if i.get("kind") in STORE_KINDS and i.get("holds_pii") is None)]
                     for k, v in sorted(by.items())])
        comp = Counter((i.get("complexity"), i.get("complexity_source") or "unknown") for i in inv if i.get("complexity"))
        md += ["\nComplexity (by source): " + ", ".join(f"{k}/{s}: {v}" for (k, s), v in comp.items()) + "\n\n"] if comp \
            else ["\nComplexity: not assessed — no Lakebridge Analyzer output; `complexity` left null.\n\n"]
        md += table(["Store", "Kind", "Layer", "Volume", "Holds PII", "Evidence"],
                    [[i.get("name"), i.get("kind"), i.get("layer_guess"), volume(i), i.get("holds_pii"), ev(i)] for i in stores], 25, "Inventory")
    else:
        md += [gap("code, DDL or scanner output (L2–L3)", "a migration scoped against a partial map of where data lives")]

    md += ["\n## 4. Workload catalogue\n\n"]
    wl = [i for i in inv if i.get("kind") not in STORE_KINDS]
    if wl:
        md += [f"{len(wl)} workloads · {sum(1 for i in wl if not i.get('owner'))} with no owner recorded — "
               f"a wave cannot take a workload nobody owns.\n\n"]
        md += table(["Workload", "Kind", "Frequency", "Volume", "Owner", "Evidence"],
                    [[i.get("name"), i.get("kind"), i.get("schedule"), volume(i), i.get("owner") or "NOT SET", ev(i)] for i in wl], 40, "Inventory")
    else:
        md += [gap("pipelines, jobs, procedures, endpoints or reports in the inventory, with schedule and owner",
                   "waves are sized without knowing what runs, how often, or who answers for it")]

    md += ["\n## 5. Data dependencies & lineage, including external services\n\n"]
    if edges:
        ids = {i.get("id"): i for i in inv}
        md += ["Edges: " + " · ".join(f"{k} {v}" for k, v in sorted(Counter(e.get("kind") for e in edges).items())) + "\n\n"]
        ext = [[i.get("name"), i.get("kind"), ev(i)] for i in inv if i.get("kind") == "external_consumer"]
        for x in sorted({e.get(s) for e in edges for s in ("from", "to")} - set(ids) - {None}):
            e = next(e for e in edges if x in (e.get("from"), e.get("to")))
            ext.append([x, "not in inventory", ev(e)])
        md += ["**External services and unmapped ends**\n\n"] + table(["Name", "Kind", "Evidence"], ext, 25, "Dependencies") if ext \
            else ["No external service or unmapped end found.\n"]
        nid = lambda x: re.sub(r"[^A-Za-z0-9_]", "_", str(x))
        lbl = lambda x: str((ids.get(x) or {}).get("name") or x).replace('"', "'")
        md += ["\n```mermaid\ngraph LR\n"] + [f'  {nid(e.get("from"))}["{lbl(e.get("from"))}"] -->|{e.get("kind")}| {nid(e.get("to"))}["{lbl(e.get("to"))}"]\n'
                                              for e in edges[:60]] + ["```\n"]
    else:
        md += [gap("code or scanner output that shows reads and writes", "a wave ships without something it depends on")]

    # ---------- Part B ----------
    md += ["\n# Part B — Assessment\n", "\n## 6. Governance, PII & GDPR gaps\n\n"]
    pii = [i for i in inv if i.get("holds_pii")]
    unreached = [i for i in pii if i.get("erasure_reaches") is not True]
    gov = [f for f in fnd if f.get("category") == "governance"]
    if stores or gov:
        md += [f"{len(pii)} surfaces hold personal data; erasure is not proven to reach {len(unreached)} of them; "
               f"{sum(1 for i in stores if i.get('holds_pii') is None)} stores are not yet classified.\n\n"]
        md += table(["Surface", "Kind", "Erasure reaches", "Evidence"],
                    [[i.get("name"), i.get("kind"), "no" if i.get("erasure_reaches") is False else "unknown", ev(i)] for i in unreached], 25, "Inventory")
        md += (["\n"] + table(["#", "Severity", "Finding", "When migrated", "Evidence"],
                              [[f.get("id"), f.get("severity"), f.get("title"), f.get("migration_disposition") or "NOT SET", ev(f)]
                               for f in sorted(gov, key=finding_order)], 15, "Findings")) if gov else []
    else:
        md += [gap("a data-surface inventory with holds_pii and erasure_reaches", "a deletion or residency obligation the target cannot meet")]

    md += ["\n## 7. Databricks security posture\n\n"]
    if scores["security"]:
        r = rd["security"]
        md += [f"**Score: {scores['security']} / 5** — {r.get('rationale')} [{r.get('basis')}: {locs(r)}]\n\n"]
    else:
        md += ["**Not scored — needs a SAT run** (or workspace evidence at L4). The gaps below come from "
               "reading code and configuration; they are not a posture score.\n\n"]
    sec = [f for f in fnd if f.get("category") == "security"]
    md += table(["#", "Severity", "Gap", "When migrated", "Evidence"],
                [[f.get("id"), f.get("severity"), f.get("title"), f.get("migration_disposition") or "NOT SET", ev(f)]
                 for f in sorted(sec, key=finding_order)], 15, "Findings") or ["No security finding recorded.\n"]

    md += ["\n## 8. Technical debt register\n\n"]
    if fnd:
        disp = Counter(f.get("migration_disposition") or "NOT SET" for f in fnd)
        md += ["All findings — when migrated: " + " · ".join(f"{k} {v}" for k, v in sorted(disp.items())) + "  \n",
               "Evidence: " + " · ".join(f"{k} {v}" for k, v in sorted(Counter(evidence_kind(f) for f in fnd).items())) + "\n\n"]
        md += table(["#", "Severity", "Category", "Layer", "Debt", "When migrated", "Evidence"],
                    [[f.get("id"), f.get("severity"), f.get("category"), f.get("layer"), f.get("title"),
                      f.get("migration_disposition") or "NOT SET", ev(f)]
                     for f in sorted((f for f in fnd if f.get("category") not in ("security", "governance")), key=finding_order)], 25, "Findings")
    else:
        md += [gap("findings from legacy-etl-archaeology or requirements-extraction", "debt a faithful migration would carry over unseen")]

    md += ["\n## 9. Migration complexity & scope\n\n"]
    if rat:
        # Scope is the decision this report exists to settle, so it leads with how much of it is
        # actually settled. An undecided share is a number the reader can act on; a table is not.
        dec = sum(1 for r in rat if r.get("disposition") in DISPOSITIONS and r.get("disposition") != "defer")
        md += [f"**{dec} of {len(rat)} objects decided ({dec * 100 // max(len(rat), 1)}%). "
               f"{len(rat) - dec} undecided or deferred; {sum(1 for r in rat if r.get('blocking'))} blocked on an open question.** "
               f"In scope: migrate + modernize; out: retire; deferred: not yet in or out.\n\n"]
        by = defaultdict(Counter)
        for r in rat:
            by[r.get("kind", "?")][r.get("disposition") or "undecided"] += 1
        md += ["| Kind | " + " | ".join(DISPOSITIONS) + " | undecided |\n|---|" + "---|" * 5 + "\n"]
        md += [f"| {k} | " + " | ".join(str(c.get(d, 0)) for d in DISPOSITIONS) + f" | {c.get('undecided', 0)} |\n" for k, c in by.items()]
        cx = lambda r: (lambda c: f"{c.get('complexity')} ({c.get('complexity_source') or 'unknown'})" if c.get("complexity") else None)(r.get("criteria") or {})
        md += ["\n"] + table(["Object", "Kind", "Disposition", "Complexity (source)", "Wave", "Blocked by"],
                             [[r.get("name"), r.get("kind"), r.get("disposition") or "undecided", cx(r), r.get("wave"), ", ".join(r.get("blocking", []))]
                              for r in sorted(rat, key=lambda r: (r.get("wave") is None, r.get("wave") or 0))], 30, "Rationalization")
        ret = [r for r in rat if r.get("disposition") == "retire"]
        md += [f"\nRetire recommendations: {len(ret)} (owner agreed: {sum(1 for r in ret if (r.get('criteria') or {}).get('owner_agreed'))}).\n"]
        manual = sum(1 for r in rat if (r.get("criteria") or {}).get("complexity_source") not in (None, "analyzer"))
        if manual:
            md += [f"\n> {manual} objects carry a manually triaged complexity tier — not measured. Run Lakebridge Analyzer before estimating.\n"]
    else:
        md += [gap("rationalization.jsonl from assessment-synthesis §1", "scope is argued object by object in meetings instead of settled here")]
    risky = [r for r in rules if r.get("rule_status") in ("CONFLICT", "CODE-ONLY", "CONFIG-ONLY")]
    md += ["\n### Business rules at risk\n\n" + ("rule_status: " + " · ".join(f"{k} {v}" for k, v in sorted(Counter(r.get("rule_status", "?") for r in rules).items()))
                                                 if rules else "No business rule extracted yet.") + "\n\n"]
    md += table(["Rule", "Status", "Logic", "Ask"], [[f"{r.get('id')} {r.get('name')}", r.get("rule_status"), f"`{r.get('logic')}`",
                                                      ", ".join(r.get("open_questions", []))] for r in risky], 25, "Business Rules") \
        or ["No rule is CONFLICT, CODE-ONLY or CONFIG-ONLY.\n"]

    md += ["\n## 10. Target architecture & component mapping\n\n", A("architecture"), "\n"]
    mapped = [r for r in rat if r.get("target_component")]
    md += table(["Object", "Disposition", "Target component"], [[r.get("name"), r.get("disposition"), r.get("target_component")] for r in mapped], 30, "Rationalization") \
        or ["_No `target_component` set in rationalization.jsonl — the component mapping is not agreed yet._\n"]

    md += ["\n## 11. Recommendations, phased roadmap & cost estimate\n\n", A("roadmap"), "\n"]
    waves = defaultdict(list)
    for r in rat:
        if r.get("wave") is not None:
            waves[r["wave"]].append(r.get("name"))
    md += [f"- Wave {w}: {len(v)} objects\n" for w, v in sorted(waves.items())]
    md += ["\n### Cost estimate\n\n> An estimate: drivers and a range with the assumptions it rests on — not a price. "
           "The price is the delivery lead's.\n\n", A("drivers")]

    md += ["\n## 12. Risk register, assumptions & open decisions\n\n### Risks\n\n", A("risks"), "\n"]
    md += table(["#", "Severity", "Risk", "When migrated", "Requirements", "Questions"],
                [[f.get("id"), f.get("severity"), f.get("title"), f.get("migration_disposition") or "NOT SET",
                  ", ".join(f.get("requirements_raised", [])), ", ".join(f.get("questions_raised", []))]
                 for f in sorted((f for f in fnd if f.get("severity") in ("critical", "high")), key=finding_order)], 20, "Findings")
    md += ["\n### Assumptions\n\nEvery record resting on inference, not on a source — each is an open question until confirmed.\n\n"]
    assumed = [[r.get("id"), n, r.get("title") or r.get("name"), ", ".join(r.get("open_questions") or r.get("questions_raised") or [])]
               for n in ("requirements", "business_rules", "inventory", "findings") for r in regs[n]
               if r.get("inferred") or evidence_kind(r) == "inferred"]
    md += table(["Id", "Register", "Assumption", "Question"], assumed, 25, "Requirements") or ["No inferred record.\n"]
    md += ["\n### Open decisions\n\n"]
    md += table(["#", "Decision", "Owner", "Blocking", "Default if unanswered"],
                [[q.get("id"), q.get("question"), q.get("ask"), ", ".join(q.get("blocking", [])), q.get("default")] for q in hi]) \
        or ["None open.\n"]

    # ---------- Appendix ----------
    md += ["\n# Appendix\n", "\n## A. Evidence\n\n", md_text(root / "sufficiency.md") or "_sufficiency.md missing_\n"]
    pend = sum(1 for f in (root / "runs").glob("*/*.jsonl") for r in read_jsonl(f) if r.get("status") == "extracted") if (root / "runs").exists() else 0
    md += [f"\nEvery row in this report names its locator. Sources read: workbook tab *Sources*. "
           f"Records still `extracted` (excluded unless --include-unreviewed): {pend}.\n"]
    md += ["\n## B. Best-practice references\n\n"]
    refs = defaultdict(list)
    for recs in regs.values():
        for r in recs:
            for e in r.get("evidence", []):
                if e.get("kind") == "external":
                    refs[e.get("locator") or e.get("source_id")].append(r.get("id") or r.get("object_id"))
    md += table(["Reference", "Supports"], [[k, ", ".join(sorted(set(filter(None, v))))] for k, v in sorted(refs.items())]) \
        or ["_No external reference cited._\n"]
    md += ["\n## C. Stakeholder questionnaire\n\nOne list per person. High-impact ones are in §12; email drafts in workbook tab *Open Questions*.\n"]
    hi_ids = {q.get("id") for q in hi}
    byp = defaultdict(list)
    for q in oq:
        if q.get("status", "open") == "open":
            byp[q.get("ask") or "unassigned"].append(q)
    for p, qs in sorted(byp.items()):
        md += [f"\n**{p}** — {len(qs)}\n"]
        md += [f"- {q.get('id')}: {stem(q.get('question'))} — §12\n" if q.get("id") in hi_ids
               else f"- {q.get('id')}: {q.get('question')} [{locs(q)}]\n" for q in qs]
    return "".join(md)


def parse_author_sections(p: Path):
    """Markdown with '## decision', '## architecture', '## roadmap', '## drivers', '## risks' headings."""
    if not p or not p.exists():
        return {}
    out, key, buf = {}, None, []
    for l in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(decision|architecture|roadmap|drivers|risks)\s*$", l.strip(), re.I)
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
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir")
    ap.add_argument("--out-dir", default=None, help="default: parent of project dir")
    ap.add_argument("--include-unreviewed", action="store_true")
    ap.add_argument("--author-sections", default=None)
    ap.add_argument("--no-docx", action="store_true")
    ap.add_argument("--built-with", default=None,
                    help='one line naming the pack, skills and CLI versions, e.g. '
                         '"databricks-discovery 0.2.0 · Databricks agent skills 0.2.22 · Databricks CLI 1.18.0"')
    a = ap.parse_args()
    root = Path(a.project_dir).resolve()
    out = Path(a.out_dir).resolve() if a.out_dir else root.parent
    out.mkdir(parents=True, exist_ok=True)

    regs = load_registers(root, a.include_unreviewed)
    intake = md_text(root / "intake.md")
    axis_c = "\n".join(l for l in intake.splitlines() if l.strip().startswith(">"))
    suff_bad = [l for l in md_text(root / "sufficiency.md").splitlines() if "❌" in l or "⚠️" in l]
    author = parse_author_sections(Path(a.author_sections)) if a.author_sections else {}

    xlsx = out / f"discovery-{root.name}.xlsx"
    build_xlsx(regs, root, xlsx, axis_c, suff_bad)
    md_path = out / "assessment-report.md"
    md_path.write_text(build_md(regs, root, axis_c, suff_bad, author, a.built_with, intake), encoding="utf-8")
    print(f"wrote {xlsx}\nwrote {md_path}")
    if not a.no_docx and shutil.which("pandoc"):
        docx = out / "assessment-report.docx"
        r = subprocess.run(["pandoc", str(md_path), "-o", str(docx)], capture_output=True, text=True)
        print(f"wrote {docx}" if r.returncode == 0 else f"pandoc failed: {r.stderr.strip()}")
    elif not a.no_docx:
        print("pandoc not found — .docx skipped")


if __name__ == "__main__":
    main()
