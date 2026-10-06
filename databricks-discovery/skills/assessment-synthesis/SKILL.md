---
name: assessment-synthesis
description: "Turn completed discovery registers - requirements, business rules, inventory with usage, dependencies, findings, open questions - into decisions: a rationalization matrix (migrate / modernize / retire / defer per object), estimate drivers, target-architecture outline, risks, and the client deliverables generated from those registers (Excel workbook, assessment report in Markdown and .docx) with an evidence-sufficiency appendix. Use when asked to write the assessment report, decide what to migrate and what to retire, estimate the migration, or build the roadmap. The registers must already exist - this skill does not extract requirements or read code."
compatibility: "Python 3.9+ with openpyxl for scripts/build_deliverables.py; pandoc optional for .docx."
metadata:
  version: "0.4.0"
  parent: discovery-intake
---

# Assessment synthesis — from registers to decisions

Done means: the person in Axis C can make the decision in Axis C and defend it with evidence
someone else can check. Not: every template section has text. Twelve pages that settle scope beat
sixty that describe the current state.

**Nothing is hand-written except five author sections.** The workbook and the report are generated
by `scripts/build_deliverables.py` from `registers/`; you write `author-sections.md` with
`## decision` (≤ 400 words — the executive summary's recommendation), `## architecture` (≤ 500),
`## roadmap` (≤ 400), `## drivers` (≤ 300 — the cost estimate), `## risks` (≤ 400), and pass it in — the generator warns when a section runs over. Write for the client: name the
object ("the nightly orders load"), never the record id (`obj-38`) — the generator replaces
inventory ids with names anyway, and adds the table of contents. A statement with no
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

## 1b. Findings → what the migration does with each

Every finding gets a `migration_disposition` in `findings.jsonl`, with the target component or
design decision that justifies it:

| Disposition | Means | Needs |
|---|---|---|
| `resolved-by-target` | the target platform removes the defect by construction (a managed service replaces a hand-rolled one; Unity Catalog grants replace a shared account) | the component that resolves it, named |
| `carried` | the defect moves over as-is unless someone acts — a faithful migration reproduces it | an owner and a mitigation, and usually a requirement |
| `redesign` | the target must be designed differently for it — the pilot or a wave carries the change | the design decision, and the wave |

A finding with no disposition is not done. `carried` findings are what a "just migrate it" plan
would ship; the report lists them first — in the top 5 risks, the debt register and the risk register.

## 1c. Readiness → `readiness.jsonl`

One record per dimension — `data`, `logic`, `governance`, `security`, `operations` — with a 1–5
`score`, the `basis` it came from, a one-line `rationale` and a locator. The generator enforces the
rules (`references/report-template.md`): no locator, no score; overall is the lowest dimension;
**Security is scored only from a SAT run or workspace evidence** — reading code finds gaps, it
cannot see the posture. The security record comes from `security-posture` (it computes the score
and lists what it could not assess); do not write `RDY-security` by hand — RUN it before this step:
with the bound workspace (then its options when permissions leave it unscored), with the client's
SAT results when they have them, and with `--iac <repo>` alone when there is no workspace yet. No
workspace bound and none offered → go back to `discovery-intake` Step 2 and ask for one first; only
a person's "we have none yet" makes "not scored — needs a workspace" an honest line in §7. Elsewhere, leave `score` null and write `needs` rather than guessing: "not scored —
needs a SAT run" is a finding the client can act on, a guessed 3 is not.

## 2. Waves and pilot

Order by dependency depth, business criticality, rule certainty. Give each object in scope its
`target_component` in `rationalization.jsonl` — the component mapping in §10 is generated from it. The pilot is **a business-visible
report of moderate complexity with a clean dependency cone** — the CFO's revenue report, not the
easiest table. Each wave: objects, data prerequisites (access, CDC, conflicts settled),
reconciliation baseline, exit criterion. Waves without prerequisites are fiction.

## 3. Estimate drivers, not prices (`## drivers`)

Object counts by kind × complexity (Analyzer) · **trial transpile rate on 10–20 objects across
tiers — run it during assessment; without it give a range and say so** · count of `CONFLICT` and
high-impact `CODE-ONLY` (calendar time with owners, not effort) · critical-path re-architecture items
· sources without CDC/watermark · `CONFIG-ONLY` migration · backfill depth × volume · missing
reconciliation baselines · consumers to re-point. Each with confidence and evidence; a driver from
L1 documents is labelled a guess. The cost estimate is these drivers plus a **range** and the
assumptions it rests on — the report labels it an estimate; the price is the delivery lead's.
`## roadmap` orders the waves into phases, each with its exit criterion.

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

`load_skill` returned this skill's absolute `directory` — `scripts/` below is relative to THAT,
never to the project folder or the folder a shell happens to be in (measured 2026-10-06: an agent
probed `$S/plugin.json` and the wrong `skills/` path, got `Operation not permitted`, and gave up
on the generator). Run it as `python3 "<directory>/scripts/build_deliverables.py" …` from the
project root.

```
python3 "<directory>/scripts/build_deliverables.py" discovery/<project> --author-sections author-sections.md \
  --built-with "databricks-discovery <version> · Databricks agent skills <version> · Databricks CLI <version>"
# → discovery-<project>.xlsx · assessment-report.md · assessment-report.docx (pandoc)
```

The deliverables carry the KMS look (`scripts/theme.py`: Poppins, Electric Blue headers, zebra
rows, severity / status / disposition chips in the brand palette, a cover block on *Summary*;
`assets/reference.docx` gives the report the same face and an INTERNAL footer). Workbook headers
are plain English ("Impact if wrong", not `impact_if_wrong`); the registers keep their field
names — the Review panel keys on them. Add a new field: register name in the schema, label in
`theme.HEADERS`, nothing else.

`--built-with` names what the assessment was built on, under the report title, so a reader weeks
later can tell which skills shaped it. Fill it from what you know, and leave out what you do not:
this pack's version is in its `plugin.json`; where the skills catalog names the Databricks agent
skills and CLI versions (Velox: "Databricks (official) v…", "Databricks CLI in use: v…"), use those;
elsewhere `databricks --version` and `databricks aitools version` say. Never guess a version.

**`pandoc not found`** is a runtime gap, not a failure: the Markdown report and the workbook are
still written. Say so in one line, name the missing runtime, and offer the install once
(`brew install pandoc` · `winget install JohnMacFarlane.Pandoc` · `apt install pandoc`) — never
rewrite the report by hand to compensate, and never present the `.md` as if it were the `.docx`.

The report follows the delivery template — Part A Discovery (1 executive summary, 2 business
context and target-state requirements, 3 data landscape, 4 workload catalogue, 5 dependencies and
lineage), Part B Assessment (6 governance and PII, 7 security posture, 8 technical debt, 9
complexity and scope, 10 target architecture and component mapping, 11 roadmap and cost estimate,
12 risks, assumptions and open decisions), Appendix (evidence, best-practice references,
stakeholder questionnaire). `references/report-template.md` maps each section to its register.
Workbook tabs in reading order: Summary · Readiness · Decisions · Rationalization · Findings ·
Business Rules · Requirements · Inventory · Open Questions (grouped by person, with an email draft)
· Traceability · Dependencies · Sufficiency · Sources. §1 with §9–§12 is the decision part and must
fit five pages; if not, the assessment is describing, not deciding. Numbers carry locators; no adjective without a number; recommendations are imperative
and owned ("Retire 112 tables — owner: DBA lead, confirm by 10-01").

## Related skills

`discovery-intake`, `requirements-extraction`, `legacy-etl-archaeology` (the registers this reads) ·
Databricks' own skills for the architecture section, when listed — `databricks-unity-catalog`
(topology, tags, masks), `databricks-metric-views` (measures), `databricks-pipelines` /
`databricks-jobs` / `databricks-dabs` (ingestion, orchestration, deployment),
`databricks-serverless-migration` (compute). Name the one you used.

## References

`../discovery-intake/references/run-layout.md` · `references/report-template.md` — section ↔
register map and the `rationalization.jsonl` schema · `scripts/build_deliverables.py --help`.
