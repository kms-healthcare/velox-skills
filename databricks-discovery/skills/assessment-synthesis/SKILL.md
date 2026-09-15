---
name: assessment-synthesis
description: >
  Turn the discovery registers of a Databricks data project — requirements, business rules,
  inventory with usage, dependencies, findings, open questions — into decisions: a rationalization
  matrix (migrate / modernize / retire / defer per object), estimate drivers, target-architecture
  outline, risks, and the client deliverables generated from the registers — an Excel workbook, an
  assessment report in Markdown and .docx — with an evidence-sufficiency appendix. Use when the user
  asks to "write the assessment report", "what do we migrate and what do we retire", "estimate the
  migration", "build the roadmap / waves", "summarise discovery for the steering committee",
  "prioritise the backlog from discovery", "give me the Excel for the client", or when
  discovery-intake's sufficiency gate says the registers are ready. Also use to turn SAT output and
  system-table analysis into client-facing requirements and risks. Not for extracting requirements
  or reading code — those registers must already exist.
compatibility: Python 3.9+ with openpyxl for scripts/build_deliverables.py; pandoc optional for .docx.
metadata:
  version: "0.2.0"
parent: discovery-intake
---

# Assessment synthesis — from registers to decisions

Done means: the person in Axis C can make the decision in Axis C and defend it with evidence
someone else can check. Not: every template section has text. Twelve pages that settle scope beat
sixty that describe the current state.

**Nothing is hand-written except four author sections.** The workbook and the report are generated
by `scripts/build_deliverables.py` from `registers/`; you write `author-sections.md` with
`## decision`, `## architecture`, `## drivers`, `## risks`, and pass it in. A statement with no
record behind it is either given a record (with a locator) or deleted. Schemas:
`../discovery-intake/references/run-layout.md`.

## Gate

Synthesise from `registers/` after human merge, never from unreviewed `runs/` batches. Re-run the
sufficiency check against Axis C first; a ❌ conclusion still gets its one-sentence section, and the
executive summary names the decision that cannot yet be made and the cost of waiting.

## 1. Rationalization matrix → `rationalization.jsonl`

| Disposition | Criteria — all with evidence | Typical share |
|---|---|---|
| **retire** | no readers in a usage window ≥ 90 days incl. month-end and quarter-end; on no scheduled path; no consumer claims it; **an owner has agreed or been asked** | 20–40% of a 10-year DW |
| **migrate** | used; low/medium complexity; rules `VERIFIED` or low-impact `CODE-ONLY`; no critical-path finding | the bulk |
| **modernize** | on the critical path with a structural finding (serial chain, full rebuild, cursor); or logic that belongs in Silver / metric views rather than N copies | 10–20%, most of the value |
| **defer** | blocked on a `CONFLICT`; owned by a system being replaced; outside the decision's scope | whatever is honest |

No `retire` without usage evidence — missing log → `defer` + question, and the report says how much
scope is undecided because of it. Objects with `CONFLICT` rules cannot be `migrate`: migrating a
disputed rule faithfully delivers wrong numbers with a certificate. Complexity used here must carry
`complexity_source`; manual tiers are triage and the report says so.

## 2. Waves and pilot

Order by dependency depth, business criticality, rule certainty. The pilot is **a business-visible
report of moderate complexity with a clean dependency cone** — the CFO's revenue report, not the
easiest table. Each wave: objects, data prerequisites (access, CDC, conflicts settled),
reconciliation baseline, exit criterion. Waves without prerequisites are fiction.

## 3. Estimate drivers, not prices

Object counts by kind × complexity (Analyzer) · **trial transpile rate on 10–20 objects across
tiers — run it during assessment; without it give a range and say so** · count of `CONFLICT` and
high-impact `CODE-ONLY` (calendar time with owners, not effort) · critical-path re-architecture items
· sources without CDC/watermark · `CONFIG-ONLY` migration · backfill depth × volume · missing
reconciliation baselines · consumers to re-point. Each with confidence and evidence; a driver from
L1 documents is labelled a guess.

## 4. Target architecture outline (`## architecture`)

Domain level unless names are verified. Catalog/schema topology with the trade-off stated;
medallion placement of the *classes* of logic found (landing → bronze; conformance and
`VERIFIED`/`CODE-ONLY` rules → silver; measures → **Unity Catalog metric views**; access views →
gold); ingestion pattern per source from its change-detection mechanism; orchestration shape from
the DAG — name the parallelisable branches; security inputs from findings (PII → tags, masks;
shared accounts → service principals per job). List the decisions that are the architect's.
Object names stay `<catalog>` placeholders until agreed.

## 5. Risks and requirements from findings (`## risks`)

Every finding with `severity ≥ high` → a risk row (owner, mitigation, deadline) and usually a
requirement (`SEC-`, `NFR-`, `DR-`). SAT checks → `SEC-` with the check id as locator;
client-owned shared-responsibility items → `NFR-` marked client-owned. Cost flags from the type
module with the breaker question and the client's answer.

## 6. Generate

```
python3 scripts/build_deliverables.py discovery/<project> --author-sections author-sections.md
# → discovery-<project>.xlsx · assessment-report.md · assessment-report.docx (pandoc)
```

Workbook tabs in reading order: Summary · Decisions · Rationalization · Findings · Business Rules ·
Requirements · Inventory · Open Questions (grouped by person, with an email draft) · Traceability ·
Dependencies · Sufficiency · Sources. Report sections 1–4 (decision, decisions required, scope,
what evidence does not support) must fit five pages; if not, the assessment is describing, not
deciding. Numbers carry locators; no adjective without a number; recommendations are imperative
and owned ("Retire 112 tables — owner: DBA lead, confirm by 10-01").

## References

`../discovery-intake/references/run-layout.md` · `references/report-template.md` — section ↔
register map and the `rationalization.jsonl` schema · `scripts/build_deliverables.py --help`.
