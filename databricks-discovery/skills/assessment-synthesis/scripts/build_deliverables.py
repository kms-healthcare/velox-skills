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
# Word budgets for the four hand-written sections. The registers cap excerpts and details; without
# a cap here the prose grew to ~1,900 words and pushed the report past the twelve pages the skill
# argues for. Over budget is a warning, not an error — the author decides.
AUTHOR_CAPS = {"decision": 400, "architecture": 500, "drivers": 300, "risks": 400}


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
             "inventory_reports", "dependency_edges", "findings", "open_questions", "rationalization"]
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
        for n in ("requirements", "business_rules", "inventory", "findings"):
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
             ["Findings", len(fnd)], ["Open questions (open)", sum(1 for q in oq if q.get("status", "open") == "open")],
             ["  of which blocking (impact high)", len(hi)], [],
             ["Rationalization", ""]] + [[d, disp.get(d, 0)] for d in DISPOSITIONS + ["undecided"]] + [[],
             ["rule_status", ""]] + [[k, v] for k, v in sorted(rs.items())] + [[],
             ["Evidence gaps (❌/⚠️)", len(suff_bad)]] + [["", " — ".join(c.strip() for c in l.strip().strip("|").split("|")[:2] if c.strip())] for l in suff_bad[:10]]
    for l in lines:
        ws.append(l)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 34, 110
    for c in ws["A"]:
        c.font = Font(bold=True)

    sheet(wb, "Decisions", ["id", "question", "why", "ask", "default", "impact_if_wrong", "blocking", "evidence"],
          [[q.get("id"), q.get("question"), q.get("why"), q.get("ask"), q.get("default"), q.get("impact_if_wrong"),
            ", ".join(q.get("blocking", [])), locs(q)] for q in sorted(hi, key=lambda q: q.get("id", ""))],
          {"question": 60, "why": 50, "ask": 24, "default": 40, "evidence": 40})

    sheet(wb, "Rationalization", ["object_id", "kind", "name", "disposition", "wave", "used", "usage_window_days",
                                  "covers_month_end", "complexity", "complexity_source", "on_critical_path",
                                  "rule_status_max", "owner_agreed", "blocking", "evidence", "notes"],
          [[r.get("object_id"), r.get("kind"), r.get("name"), r.get("disposition"), r.get("wave"),
            *(r.get("criteria", {}).get(k) for k in ("used", "usage_window_days", "covers_month_end", "complexity",
                                                       "complexity_source", "on_critical_path", "rule_status_max", "owner_agreed")),
            ", ".join(r.get("blocking", [])), locs(r), r.get("notes")] for r in rat],
          {"name": 36, "evidence": 40, "notes": 40})

    sheet(wb, "Findings", ["id", "severity", "category", "title", "impact", "detail", "requirements_raised",
                           "questions_raised", "evidence", "status"],
          [[f.get("id"), f.get("severity"), f.get("category"), f.get("title"), f.get("impact"), f.get("detail"),
            ", ".join(f.get("requirements_raised", [])), ", ".join(f.get("questions_raised", [])), locs(f), f.get("status")]
           for f in sorted(fnd, key=lambda f: SEV.get(f.get("severity"), 9))],
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

    sheet(wb, "Inventory", ["id", "kind", "name", "layer_guess", "row_estimate", "size_gb", "schedule", "avg_runtime_min",
                            "run_as", "readers", "writers", "reads", "writes", "consumers", "exec_count_90d", "last_read_at",
                            "last_write_at", "last_exec_at", "orphan", "pii_candidates", "complexity", "complexity_source",
                            "disposition", "evidence", "status"],
          [[i.get("id"), i.get("kind"), i.get("name"), i.get("layer_guess"), i.get("row_estimate"), i.get("size_gb"),
            i.get("schedule"), i.get("avg_runtime_min"), i.get("run_as"), ", ".join(i.get("readers", [])), ", ".join(i.get("writers", [])),
            ", ".join(i.get("reads", [])), ", ".join(i.get("writes", [])), ", ".join(i.get("consumers", [])), i.get("exec_count_90d"),
            i.get("last_read_at"), i.get("last_write_at"), i.get("last_exec_at"), i.get("orphan"), ", ".join(i.get("pii_candidates", [])),
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
def build_md(regs, root, axis_c, suff_bad, author):
    req, rules, inv, edges, fnd, oq, rat = (regs[k] for k in
        ("requirements", "business_rules", "inventory", "dependency_edges", "findings", "open_questions", "rationalization"))
    A = lambda k: author.get(k, f"_Author section `{k}` not provided — pass --author-sections._\n")
    md = [f"# {root.name} — Discovery & Assessment\n"]
    md += ["\n## 1. Decision and recommendation\n\n", (axis_c or "> Axis C missing in intake.md") + "\n\n", A("decision")]

    hi = [q for q in oq if q.get("impact_if_wrong") == "high" and q.get("status", "open") == "open"]
    md += ["\n## 2. Decisions required\n\n| # | Decision | Owner | Blocking | Default if unanswered |\n|---|---|---|---|---|\n"]
    md += [f"| {q.get('id')} | {q.get('question')} | {q.get('ask')} | {', '.join(q.get('blocking', []))} | {q.get('default')} |\n" for q in hi] or ["| — | none open | | | |\n"]

    md += ["\n## 3. Scope — rationalization summary\n\n"]
    if rat:
        # Scope is the decision this report exists to settle, so it leads with how much of it is
        # actually settled. An undecided share is a number the reader can act on; a table is not.
        dec = sum(1 for r in rat if r.get("disposition") in DISPOSITIONS and r.get("disposition") != "defer")
        und = len(rat) - dec
        blocked = sum(1 for r in rat if r.get("blocking"))
        md += [f"**{dec} of {len(rat)} objects decided ({dec * 100 // max(len(rat), 1)}%). "
               f"{und} undecided or deferred; {blocked} blocked on an open question.**\n\n"]
        by = defaultdict(Counter)
        for r in rat:
            by[r.get("kind", "?")][r.get("disposition") or "undecided"] += 1
        md += ["| Kind | " + " | ".join(DISPOSITIONS) + " | undecided |\n|---|" + "---|" * 5 + "\n"]
        md += [f"| {k} | " + " | ".join(str(c.get(d, 0)) for d in DISPOSITIONS) + f" | {c.get('undecided', 0)} |\n" for k, c in by.items()]
        ret = [r for r in rat if r.get("disposition") == "retire"]
        md += [f"\nRetire recommendations: {len(ret)} (owner agreed: {sum(1 for r in ret if (r.get('criteria') or {}).get('owner_agreed'))}).\n"]
        md += [f"- {r.get('name')} [{locs(r)}]\n" for r in ret[:15]]
        manual = sum(1 for r in rat if (r.get("criteria") or {}).get("complexity_source") not in (None, "analyzer"))
        if manual:
            md += [f"\n> {manual} objects carry a manually triaged complexity tier — not measured. Run Lakebridge Analyzer before estimating.\n"]
    else:
        md += ["_rationalization.jsonl not present._\n"]

    md += ["\n## 4. What the evidence does not yet support\n\n"]
    if suff_bad:
        hdr = next((l for l in md_text(root / "sufficiency.md").splitlines() if l.startswith("|") and "Conclusion" in l), None)
        if hdr:
            md += [hdr + "\n", "|" + "---|" * (hdr.count("|") - 1) + "\n"]
        md += [l + "\n" for l in suff_bad]
    else:
        md += ["_no ❌/⚠️ rows in sufficiency.md — confirm that is true._\n"]

    md += ["\n## 5. Key findings\n\n| # | Severity | Finding | Impact | Evidence |\n|---|---|---|---|---|\n"]
    md += [f"| {f.get('id')} | {f.get('severity')} | {f.get('title')} | {f.get('impact', '')} | {locs(f)} |\n"
           for f in sorted(fnd, key=lambda f: SEV.get(f.get("severity"), 9))[:10]]

    dist = Counter(r.get("rule_status", "?") for r in rules)
    md += ["\n## 6. Business rules at risk\n\nrule_status: " + " · ".join(f"{k} {v}" for k, v in sorted(dist.items())) + "\n\n"]
    md += ["| Rule | Status | Logic | Ask |\n|---|---|---|---|\n"]
    md += [f"| {r.get('id')} {r.get('name')} | {r.get('rule_status')} | `{r.get('logic')}` | {', '.join(r.get('open_questions', []))} |\n"
           for r in rules if r.get("rule_status") in ("CONFLICT", "CODE-ONLY", "CONFIG-ONLY")][:25]

    c = Counter((r.get("type"), r.get("status")) for r in req)
    md += ["\n## 7. Requirements\n\n| Type | reviewed | confirmed | deferred | extracted |\n|---|---|---|---|---|\n"]
    md += [f"| {t} | " + " | ".join(str(c.get((t, s), 0)) for s in ("reviewed", "confirmed", "deferred", "extracted")) + " |\n"
           for t in ("functional", "data", "security", "nonfunctional", "scope", "integration")]
    inf = [r for r in req if r.get("inferred")]
    conf = [r for r in req if r.get("conflicts")]
    md += [f"\n{len(req)} requirements · {len(inf)} inferred, awaiting confirmation · {len(conf)} carry a source conflict.\n"]
    md += [f"- {r.get('id')} {r.get('title')} → {', '.join(r.get('open_questions', []))}\n" for r in inf[:10]]

    md += ["\n## 8. Target architecture outline\n\n", A("architecture")]
    if edges:
        md += ["\n```mermaid\ngraph LR\n"] + [f"  {re.sub(r'[^A-Za-z0-9_]', '_', str(e.get('from')))} -->|{e.get('kind')}| {re.sub(r'[^A-Za-z0-9_]', '_', str(e.get('to')))}\n" for e in edges[:60]] + ["```\n"]

    md += ["\n## 9. Waves, pilot, estimate drivers\n\n"]
    waves = defaultdict(list)
    for r in rat:
        if r.get("wave") is not None:
            waves[r["wave"]].append(r.get("name"))
    md += [f"- Wave {w}: {len(v)} objects\n" for w, v in sorted(waves.items())]
    comp = Counter((i.get("complexity"), i.get("complexity_source") or "unknown") for i in inv if i.get("complexity"))
    md += ["\nComplexity (inventory, by source): " + ", ".join(f"{k}/{s}: {v}" for (k, s), v in comp.items()) + "\n"] if comp else ["\nComplexity: not assessed — no Lakebridge Analyzer output; `complexity` left null.\n"]
    md += [A("drivers")]

    md += ["\n## 10. Risks and cost flags\n\n", A("risks")]

    # Section 2 already prints the high-impact questions in full. Repeating them here doubled the
    # longest section of the report, so this is a routing list: who to ask, what about, where the
    # full text lives (§2, or the workbook tab *Open Questions*, which carries the email draft).
    md += ["\n## 11. Open questions by person\n\nRouting list. Full text: §2 for high-impact, workbook tab *Open Questions* for all.\n"]
    hi_ids = {q.get("id") for q in hi}
    byp = defaultdict(list)
    for q in oq:
        if q.get("status", "open") == "open":
            byp[q.get("ask") or "unassigned"].append(q)
    for p, qs in sorted(byp.items()):
        md += [f"\n**{p}** — {len(qs)}\n"]
        for q in qs:
            if q.get("id") in hi_ids:
                md += [f"- {q.get('id')}: {stem(q.get('question'))} — full text §2\n"]
            else:
                md += [f"- {q.get('id')}: {stem(q.get('question'))} [{locs(q)}]\n"]

    md += ["\n## Appendix C — Evidence sufficiency\n\n", md_text(root / "sufficiency.md") or "_missing_\n"]
    pend = sum(1 for f in (root / "runs").glob("*/*.jsonl") for r in read_jsonl(f) if r.get("status") == "extracted") if (root / "runs").exists() else 0
    md += [f"\n## Appendix D — Sources\n\nRecords still `extracted` (excluded unless --include-unreviewed): {pend}. Full list: workbook tab *Sources*.\n"]
    return "".join(md)


def parse_author_sections(p: Path):
    """Markdown with '## decision', '## architecture', '## drivers', '## risks' headings."""
    if not p or not p.exists():
        return {}
    out, key, buf = {}, None, []
    for l in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(decision|architecture|drivers|risks)\s*$", l.strip(), re.I)
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
    md_path.write_text(build_md(regs, root, axis_c, suff_bad, author), encoding="utf-8")
    print(f"wrote {xlsx}\nwrote {md_path}")
    if not a.no_docx and shutil.which("pandoc"):
        docx = out / "assessment-report.docx"
        r = subprocess.run(["pandoc", str(md_path), "-o", str(docx)], capture_output=True, text=True)
        print(f"wrote {docx}" if r.returncode == 0 else f"pandoc failed: {r.stderr.strip()}")
    elif not a.no_docx:
        print("pandoc not found — .docx skipped")


if __name__ == "__main__":
    main()
