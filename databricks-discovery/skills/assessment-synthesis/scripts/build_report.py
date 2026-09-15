#!/usr/bin/env python3
"""Render assessment-report.md and rationalization-summary.md from discovery registers.

Usage:
  python3 build_report.py <discovery/project dir> [--out assessment-report.md] [--include-unreviewed]

Reads registers/*.jsonl (+ rationalization.jsonl if present), intake.md, sufficiency.md.
Stdlib only. Records with status 'extracted' are excluded unless --include-unreviewed.
Every emitted number is followed by the locators it rests on.
"""
import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path


def read_jsonl(p: Path):
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.stderr.write(f"warn: {p.name}:{i} bad json: {e}\n")
    return out


def locs(rec):
    ev = rec.get("evidence") or []
    ls = [e.get("locator") for e in ev if e.get("locator")]
    return " [" + "; ".join(ls) + "]" if ls else " [NO LOCATOR]"


def reviewed(recs, include_unreviewed):
    if include_unreviewed:
        return recs
    return [r for r in recs if r.get("status") in ("reviewed", "confirmed", "deferred")]


def section(title):
    return f"\n## {title}\n\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--out", default="assessment-report.md")
    ap.add_argument("--include-unreviewed", action="store_true")
    a = ap.parse_args()
    root = Path(a.project_dir)
    reg = root / "registers"
    inc = a.include_unreviewed

    req = reviewed(read_jsonl(reg / "requirements.jsonl"), inc)
    rules = reviewed(read_jsonl(reg / "business_rules.jsonl"), inc)
    findings = reviewed(read_jsonl(reg / "findings.jsonl"), inc)
    oq = read_jsonl(reg / "open_questions.jsonl")
    inv = []
    for k in ("tables", "pipelines", "reports"):
        inv += reviewed(read_jsonl(reg / f"inventory_{k}.jsonl"), inc)
    rat = read_jsonl(reg / "rationalization.jsonl")
    pending = sum(1 for f in reg.glob("*.jsonl") for r in read_jsonl(f) if r.get("status") == "extracted")

    intake = (root / "intake.md").read_text(encoding="utf-8") if (root / "intake.md").exists() else ""
    suff = (root / "sufficiency.md").read_text(encoding="utf-8") if (root / "sufficiency.md").exists() else ""

    md = [f"# {root.name} — Discovery & Assessment\n"]

    md.append(section("1. Decision and recommendation"))
    axis_c = [l for l in intake.splitlines() if l.strip().startswith(">")]
    md.append("\n".join(axis_c) if axis_c else "> Axis C sentence missing from intake.md — fix before circulating.\n")
    md.append("\n\nRecommendation: _(author writes here, citing §3 and §5)_\n")

    md.append(section("2. Decisions required"))
    hi = [q for q in oq if q.get("impact_if_wrong") == "high" and q.get("status", "open") == "open"]
    md.append("| # | Decision | Owner | Blocking | Default if unanswered |\n|---|---|---|---|---|\n")
    for q in sorted(hi, key=lambda q: q.get("id", "")):
        md.append(f"| {q.get('id')} | {q.get('question')} | {q.get('ask')} | {', '.join(q.get('blocking', []))} | {q.get('default')} |\n")
    if not hi:
        md.append("| — | no high-impact open questions | | | |\n")

    md.append(section("3. Scope — rationalization summary"))
    if rat:
        by = defaultdict(Counter)
        for r in rat:
            by[r.get("kind", "?")][r.get("disposition", "undecided")] += 1
        cols = ["migrate", "modernize", "retire", "defer"]
        md.append("| Kind | " + " | ".join(cols) + " | undecided |\n|---|" + "---|" * (len(cols) + 1) + "\n")
        for k, c in by.items():
            und = sum(v for d, v in c.items() if d not in cols)
            md.append(f"| {k} | " + " | ".join(str(c.get(d, 0)) for d in cols) + f" | {und} |\n")
        ret = [r for r in rat if r.get("disposition") == "retire"]
        md.append(f"\nRetire recommendations: {len(ret)}; owner agreed: {sum(1 for r in ret if r.get('criteria', {}).get('owner_agreed'))}.\n")
        for r in ret[:15]:
            md.append(f"- {r.get('name')}{locs(r)}\n")
    else:
        md.append("_No rationalization.jsonl — matrix not yet built._\n")

    md.append(section("4. What the evidence does not yet support"))
    bad = [l for l in suff.splitlines() if "❌" in l or "⚠️" in l]
    md.append("\n".join(bad) if bad else "_sufficiency.md has no ❌/⚠️ rows — verify that is true, not just unwritten._\n")

    md.append(section("5. Key findings"))
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    md.append("| # | Severity | Finding | Impact | Evidence |\n|---|---|---|---|---|\n")
    for f in sorted(findings, key=lambda f: sev.get(f.get("severity"), 9))[:10]:
        md.append(f"| {f.get('id')} | {f.get('severity')} | {f.get('title')} | {f.get('impact','')} |{locs(f)} |\n")

    md.append(section("6. Business rules at risk"))
    dist = Counter(r.get("rule_status", "?") for r in rules)
    md.append("rule_status: " + " · ".join(f"{k} {v}" for k, v in sorted(dist.items())) + "\n\n")
    md.append("| Rule | Status | Logic | Ask |\n|---|---|---|---|\n")
    for r in [r for r in rules if r.get("rule_status") in ("CONFLICT", "CODE-ONLY", "CONFIG-ONLY")][:25]:
        ask = ", ".join(r.get("open_questions", []))
        md.append(f"| {r.get('id')} {r.get('name')} | {r.get('rule_status')} | `{r.get('logic')}` | {ask} |\n")

    md.append(section("7. Requirements"))
    c = Counter((r.get("type"), r.get("status")) for r in req)
    md.append("| Type | reviewed | confirmed | deferred |\n|---|---|---|---|\n")
    for t in ("functional", "data", "security", "nonfunctional", "scope", "integration"):
        md.append(f"| {t} | {c.get((t,'reviewed'),0)} | {c.get((t,'confirmed'),0)} | {c.get((t,'deferred'),0)} |\n")
    inf = [r for r in req if r.get("inferred")]
    md.append(f"\nInferred requirements awaiting confirmation: {len(inf)}\n")
    for r in inf[:10]:
        md.append(f"- {r.get('id')} {r.get('title')} → {', '.join(r.get('open_questions', []))}\n")

    md.append(section("8. Target architecture outline"))
    md.append("_Author section. Object names remain `<catalog>` placeholders until agreed._\n")

    md.append(section("9. Waves, pilot, estimate drivers"))
    if rat:
        waves = defaultdict(list)
        for r in rat:
            if r.get("wave") is not None:
                waves[r["wave"]].append(r.get("name"))
        for w in sorted(waves):
            md.append(f"- Wave {w}: {len(waves[w])} objects\n")
    comp = Counter((i.get("complexity"), i.get("complexity_source") or "unknown") for i in inv if i.get("complexity"))
    md.append("\nComplexity tiers (inventory, by source): " + ", ".join(f"{k}/{src}: {v}" for (k, src), v in comp.items()) + "\n")
    if any(src != "analyzer" for (_, src) in comp):
        md.append("\n> Tiers not marked `analyzer` are manual triage, not measured — run Lakebridge Analyzer before using them for estimates.\n")

    md.append(section("10. Risks and cost flags"))
    md.append("_Author section: findings severity ≥ high → risk rows with owner and deadline._\n")

    md.append(section("11. Open questions by person"))
    byp = defaultdict(list)
    for q in oq:
        if q.get("status", "open") == "open":
            byp[q.get("ask", "unassigned")].append(q)
    for p, qs in sorted(byp.items()):
        md.append(f"\n**{p}**\n")
        for q in qs:
            md.append(f"- {q.get('id')}: {q.get('question')}{locs(q)}\n")

    md.append(section("Appendix C — Evidence sufficiency"))
    md.append(suff or "_missing_\n")
    md.append(section("Appendix D — Sources and pending review"))
    md.append(f"Records still `extracted` (excluded above): {pending}\n")

    (root / a.out).write_text("".join(md), encoding="utf-8")
    print(f"wrote {root / a.out}")


if __name__ == "__main__":
    main()
