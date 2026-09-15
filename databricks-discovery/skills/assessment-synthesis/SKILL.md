---
name: assessment-synthesis
description: >
  Turn the discovery registers of a Databricks data project — requirements, business rules,
  inventory with usage, dependencies, findings, open questions — into decisions: a rationalization
  matrix (migrate / modernize / retire / defer per object), estimate drivers, target-architecture
  outline, risks, and an assessment report written as a decision instrument with an
  evidence-sufficiency appendix. Use when the user asks to "write the assessment report", "what do
  we migrate and what do we retire", "estimate the migration", "build the roadmap / waves",
  "summarise discovery for the steering committee", "prioritise the backlog from discovery", or
  when discovery-intake's sufficiency gate says the registers are ready. Also use to turn SAT
  output and system-table analysis into client-facing requirements and risks. Not for extracting
  requirements or reading code — those registers must already exist.
compatibility: Runs outside Databricks. Filesystem; Python 3.9+ recommended for generating the report and matrix from JSONL.
metadata:
  version: "0.1.0"
parent: discovery-intake
---

# Assessment synthesis — from registers to decisions

## What "done" means here

The assessment is done when the person named in Axis C can make the decision named in Axis C,
and can defend it with evidence someone else can check. It is not done when every section of a
template has text in it. A 12-page report that settles scope beats a 60-page report that
describes the current state.

Everything in the report is **generated from the registers**. If a statement in the report has no
record behind it, either add the record (with a locator) or delete the statement.

## Inputs — and the gate before starting

From `discovery/<project>/`: `intake.md` (Axis C is the spec for this skill), `sufficiency.md`,
and `registers/*.jsonl` after human merge. Do **not** synthesise from `runs/` batches that have not
been reviewed — the report would carry `extracted` records as if they were confirmed.

Before writing, re-run the sufficiency check against Axis C. If a core conclusion is ❌, the report
still gets written — with that section as the one-sentence "insufficient evidence" form — and the
executive summary says which decision cannot yet be made and what it costs to wait.

## Step 1 — Rationalization matrix

Every inventory object (`tbl-`, `pipe-`, `rpt-`) receives a `disposition`. This is the centre of
a migration or consolidation assessment and a major input for cost and greenfield types.

| Disposition | Criteria (all must have evidence) | Typical share |
|---|---|---|
| **retire** | No readers in a usage window ≥ 90 days incl. month-end and quarter-end; not on any scheduled path; no downstream consumer claims it; **an owner has agreed or been asked** | 20–40% in a 10-year DW |
| **migrate** (as-is, transpile) | Used; low/medium complexity; rules `VERIFIED` or `CODE-ONLY` with low impact; no critical-path finding | the bulk |
| **modernize** (re-architect) | On the critical path with a structural finding (serial chain, full rebuild, cursor over large table); or embodies logic that belongs in Silver/metric views rather than 14 copies; or high complexity where transpiling reproduces the problem | 10–20%, and most of the value |
| **defer** | Used but owned by a system being replaced anyway; blocked on an unresolved `CONFLICT`; or outside the decision's scope | whatever is honest |

Rules:
- `retire` without usage evidence is not allowed. If the log is missing, the disposition is
  `defer` with an open question — and the report says how much scope is undecided because of it.
- Each `retire` has a named owner in `open_questions` who has to say yes. Retiring is a business
  decision the assessment *recommends*.
- Objects whose rules are `CONFLICT` cannot be `migrate` until the conflict is settled — mark
  `defer` and link the question. Migrating a disputed rule faithfully is how wrong numbers reach
  the new platform with a certificate.
- Write the matrix as `rationalization.jsonl` (object id, disposition, criteria met, evidence
  locators, blocking questions) and render a summary table by kind × disposition.

## Step 2 — Waves and the pilot

Order by dependency depth (from `dependency_edges.jsonl`), business criticality (from usage and
Axis C), and rule certainty. The pilot is **a business-visible report with moderate complexity and
a clean dependency cone** — enough to prove reconciliation, not so trivial that success proves
nothing. "Start with the easiest table" is the wrong pilot; "start with the CFO's revenue report"
is usually right.

Each wave lists: objects, prerequisites (access, CDC enabled, conflicts settled), the reconciliation
baseline, and the exit criterion. Waves without data prerequisites are fiction.

## Step 3 — Estimate drivers, not prices

The assessment produces **drivers**; the delivery lead prices them. Drivers with evidence:

| Driver | From |
|---|---|
| Object counts by kind × complexity tier | Lakebridge Analyzer / inventory |
| Trial automation rate | Lakebridge Transpiler on a 10–20 object sample across tiers — **run it during assessment**; without it, give a range and say so |
| Number of `CONFLICT` + high-impact `CODE-ONLY` rules | Each is a decision cycle with a business owner: calendar time, not effort |
| Critical-path findings requiring re-architecture | Each is design work, not conversion |
| Sources without CDC / reliable watermark | Snapshot-diff or hash strategies; history negotiation |
| Objects with `CONFIG-ONLY` rules | Config migration + ownership setup |
| Backfill depth and volume | Row counts × history requirement |
| Missing reconciliation baselines | Unbounded UAT |
| Consumers to re-point | Reports, Excel/ODBC, downstream systems |

State the confidence of each driver and the evidence behind it. A driver from L1 documents is a
guess and is labelled as one.

## Step 4 — Target architecture outline

Domain-level, not table-level, unless verified names exist:
- Catalog / schema topology proposal (per environment or per domain — state the trade-off).
- Medallion placement of the *classes* of logic found: raw landing (bronze), conformance and the
  rules that were `VERIFIED`/`CODE-ONLY` (silver), metrics — proposed as **Unity Catalog metric
  views** where the rule is a measure definition — and access views (gold).
- Ingestion pattern per source from its change-detection mechanism (Lakeflow Connect, Auto Loader,
  snapshot).
- Orchestration shape from the dependency graph: the serial chain becomes a DAG; name the
  parallelisable branches from the edges.
- Security model inputs: PII findings → tags, row filters, column masks; shared-account findings →
  service principals per job.
- Everything else is the architect's call; list the decisions that are theirs.

Object names are placeholders until verified. `minhphat_prod.silver.transactions` is fine **only**
if the client has agreed the catalog name; otherwise `<catalog>.silver.transactions`.

## Step 5 — Risks, and requirements from findings

Each `finding` with `severity ≥ high` becomes either a risk row (owner, mitigation, deadline) or a
requirement (`SEC-`, `NFR-`, `DR-`) — usually both. SAT output maps the same way: SAT check →
`SEC-` requirement with the SAT check id as locator; shared-responsibility items the client owns
(backup, DR, identity) → `NFR-` with "client-owned" stated.

Cost-risk flags from the project-type module go here with the breaker question and the client's
answer, if given.

## Step 6 — The report

Generated from registers by `scripts/build_report.py` (or by hand following
`references/report-template.md`). Order is fixed because the reader's attention is not:

1. **Decision and recommendation** — one page. The Axis C sentence, the answer, the conditions.
2. **Decisions required from the client** — table: decision, owner, deadline, cost of delay.
3. **Scope: rationalization summary** — counts by disposition with the biggest retire/modernize
   items named; link to the full matrix.
4. **What the evidence does not yet support** — from `sufficiency.md`. Up front, not in the appendix
   only, because it changes how the reader weighs everything else.
5. **Key findings by impact** — top 10 from `findings.jsonl`, each with locator and consequence.
6. **Business rules at risk** — `CONFLICT` and high-impact `CODE-ONLY` lists with owners.
7. **Requirements by type** — counts, and the must-haves with status.
8. **Target architecture outline** and the architect's open decisions.
9. **Waves, pilot, estimate drivers**.
10. **Risks and cost flags**.
11. **Open questions by person** — so each stakeholder can find their list.
12. **Appendices** — full matrix, traceability (requirement → rule → object → question),
    sufficiency table, sources and manifest, method notes (code-first, usage window, calibration
    error rate).

Length target: sections 1–4 fit in five pages. If they do not, the assessment has not decided
enough.

## Language and tone

Report in the user's working language; identifiers verbatim. Numbers carry locators in footnotes
or a trailing `[src-…]`. No adjectives without a number ("significant duplication" → "112 of 340
tables have no reader in 13 months [src-usage-01]"). Recommendations are imperative and owned
("Retire 112 tables — owner: DBA lead, confirm by 10-01").

## Failure modes

| Failure | Sign |
|---|---|
| Describing instead of deciding | No "decisions required" table; executive summary restates the intake |
| Retire without usage evidence | `retire` rows whose evidence is a spec or an interview |
| Migrating disputed rules | `CONFLICT` rules inside `migrate` objects |
| Prices instead of drivers | A currency figure with no driver table |
| Template completeness | Sections with text but no register behind them |
| Names that look real | Catalog names in the architecture section that nobody agreed |
| Sufficiency buried | ❌ items only in the appendix |

## Reference files

- `../discovery-intake/references/run-layout.md` — register schemas. Required.
- `references/report-template.md` — section-by-section template with the register each section
  pulls from, and the `rationalization.jsonl` schema.
- `scripts/build_report.py` — renders `assessment-report.md` and `rationalization-summary.md`
  from `registers/` (stdlib only). Read `--help`.
