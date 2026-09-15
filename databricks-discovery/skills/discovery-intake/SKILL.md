---
name: discovery-intake
description: >
  Mandatory entry point for the discovery & assessment phase of a data project on Databricks.
  Identifies the project type from the real driver, inventories what inputs exist, pins down the
  decision the assessment must serve, then produces the source request list, an evidence-sufficiency
  gate, and confirmation questions before handing off to requirements extraction, legacy code
  archaeology, or report synthesis. Use this skill as soon as a user starts a new data or Databricks
  project, or mentions discovery, assessment, current-state review, evaluating a legacy system,
  migrating a data warehouse / SSIS / Informatica / Teradata / SQL Server to Databricks, consolidating
  workspaces, rising Databricks cost, building a new lakehouse, streaming, ML platform, Delta Sharing,
  or hands over a pile of client documents / stored procedures / DDL and asks "where do I start",
  "what should I ask the client", "how do I estimate this", "write the assessment report". Trigger
  even when the words discovery or assessment are absent — "client wants to move to Databricks",
  "boss asked me to evaluate system X", "we have 300 stored procs to understand" all belong here.
  Do not use for writing pipelines, deploying bundles, tuning queries, or operating a workspace.
compatibility: Runs outside Databricks (Claude Code or equivalent). Databricks CLI + managed MCP optional. Python 3.9+ and openpyxl for the deliverables generator; pandoc optional for .docx.
metadata:
  version: "0.2.0"
  audience: engineers who also own requirements on data projects
---

# Discovery intake — the entry point for every assessment

Assessments fail one way: someone fills every section of a template and the result describes
everything but **helps nobody decide anything**. Three things were never settled: *what kind of
project this is*, *what evidence exists*, *who decides what with the result*. This skill settles
them, then hands off to `requirements-extraction`, `legacy-etl-archaeology`, `assessment-synthesis`.

The user is an engineer who also owns requirements. They lack no technical skill — they lack the
discipline to stop and ask before building. Write for that: no lectures, plain statements of what
to ask, what to request, what cannot yet be concluded. Artifacts in the user's language;
identifiers verbatim.

## Three rules, never broken

1. **Do not invent.** No table, column, catalog, job, or system name that evidence has not shown;
   no number without a `locator`. Use `<catalog>.<schema>.<table>`, `<source system>` until
   verified. Invented names look real, get copied into code, and surface in front of the client.
2. **Separate "the source says" from "I infer".** Every current-state statement is `stated`
   (locator) or `inferred` (basis given, and an open question raised). Conclusions rest on `stated`.
3. **Deliver while asking.** Each turn: deliver everything that does not depend on an answer,
   then ask **≤ 5 blocking questions**, each with *why · recommended default · what breaks if wrong ·
   who to ask*. Users abandon a skill after the second interrogation.

**First turn on thin input** ("client wants SQL Server → Databricks, I have some procs, where do I
start?"): classify provisionally, record input levels, propose an Axis C sentence to edit, emit the
source request, attach ≤ 5 questions. Never answer "give me more information".

## Cost discipline

Read `references/run-layout.md` once; load **one** project-type module; do not copy source files
(reference by path + sha256); respect the record budget in run-layout; produce **one** report — the
generator's — and write only the four author sections. Last iteration spent a quarter of its output
on a second hand-written report and 32 file copies. None of it improved the assessment.

---

## Step 1 — Three-axis intake → `intake.md`

### Axis A — project type, via the real driver

Do not ask "what kind of project". Ask: **"Why now? If nothing is done, what happens in 12 months?"**

| Type | Signals | Real driver usually | Module |
|---|---|---|---|
| 1 Migration / modernization | legacy, license ending, Teradata/Oracle/SQL Server/SSIS/Informatica, "move to" | license cost, cannot scale, the one expert is leaving | `project-type-migration.md` |
| 2 Greenfield lakehouse | nothing central, Excel everywhere, "we want a platform" | one stuck use case, or "we need AI" | `project-type-greenfield.md` |
| 3 Platform / consolidation | many workspaces, merger, permissions a mess, hive_metastore | duplicate spend, audit, M&A | `project-type-consolidation.md` |
| 4 Cost & performance | bill rising, jobs overrun, dashboards slow | budget cut, SLA broken, CFO asking | `project-type-cost-performance.md` |
| 5 Real-time / streaming | real-time, Kafka, events, minutes | an operational action — or a wish | `project-type-streaming.md` |
| 6 ML / AI platform | models in notebooks, RAG, agents, GenAI on our data | cannot reach production; leadership pressure | `project-type-ml-ai.md` |
| 7 Data sharing | partners, sell data, Delta Sharing, clean room | contract, partner requirement | `project-type-sharing.md` |

Two types heard → primary by real driver, other `secondary`; load both modules. Stated driver ≠
type → first finding. Unclassifiable after two rounds → `unknown`, run migration module, question #1.

### Axis B — inputs available, **per source system**

| Level | Exists | Can conclude | Cannot — say so |
|---|---|---|---|
| L0 | user's words | provisional type, source request, questions | any number, any quality/complexity judgement |
| L1 | documents, transcripts, tickets | `stated` requirements, glossary, goals | the running system — docs describe the design |
| L2 | code / DDL / ETL artifacts | running rules, dependencies, complexity, doc-vs-code conflicts | volume, usage, data quality |
| L3 | source access or scanner output (Lakebridge Analyzer, catalogs, query logs) | inventory, real usage, orphans, volume | business meaning, keep/drop |
| L4 | Unity Catalog, system tables, workspace | cost baseline, lineage, security posture (SAT) | what *should* exist — Axis C |

At L0–L1 every current-state section reads *"no evidence yet — needs [source]"*.

### Axis C — the decision

> "This report is for **[who]** to decide **[what]** before **[when]**."

Go/no-go → feasibility, blockers, prerequisites · Scope → rationalization matrix · Budget → effort
drivers, cost baseline · Architecture → options with prices · Tool → criteria and scores. Missing?
Ask *"after reading it, what will you do differently?"* No action → no assessment yet; say so.

## Step 2 — Source request → `source_request.md`

Load the module; it lists sources in **required / recommended / optional** tiers with *why* and *how
to obtain*. Mark received sources with a locator; for each missing required source, name the
conclusion that will be absent. Two universals: **scanner output beats human documents** (tools
describe the running system; documents describe a design), and **request access on day one** —
the longest lead item.

## Step 3 — Evidence-sufficiency gate → `sufficiency.md`

| Conclusion (from Axis C) | Evidence required | In hand (locator) | State |
|---|---|---|---|
| "230 of 340 tables migrate" | inventory + usage ≥ 90 days incl. month-end | analyzer ✅ · usage ❌ | ❌ |
| "effort ≈ N" | complexity + trial transpile rate | complexity ✅ · trial ❌ | ⚠️ range only |

❌ → the report section is one sentence: *insufficient evidence; needs X; risk if skipped Y*.
⚠️ → a range or a condition, never a point value. Always include the **usage window row** (source,
start, end, last restart if DMV-based). The table goes in the report appendix — it is what makes
the client trust the rest. Agents fill gaps with plausible prose; this table forces gaps to show.

## Step 4 — Confirmation questions → `open_questions.jsonl`

Generated from contradictions and gaps, never from a template. Weak: "how does revenue work?"
Strong: "`sp_Calc_Daily_Revenue:45-52` excludes `HCM-99` and `status = 9`; spec §4.1 mentions
neither. Still valid, and who decides?" Fields: `question · why · evidence · ask (a person) ·
default · impact_if_wrong · blocking`. ≤ 5 to the user per turn, ordered by `impact_if_wrong`.

## Step 5 — Hand-off

| In hand | Hand to | Returns |
|---|---|---|
| documents, transcripts (L1) | `requirements-extraction` | `requirements`, `findings`, `open_questions` |
| procs, SSIS, SQL, schedulers (L2) | `legacy-etl-archaeology` | `business_rules`, `inventory`, `dependency_edges`, `findings` |
| scanner output (L3–L4) | the type module says how to read it | `inventory`, `findings` |
| registers pass the gate | `assessment-synthesis` | `rationalization`, workbook, report |

After each return, update `sufficiency.md` and the question list. Discovery is a loop.

## Layout, review, and client-data constraints

`discovery/<project>/` per `references/run-layout.md`. The agent writes only into `runs/<run>/`;
a human reviews `review.md` and merges into `registers/`. Deliverables (`discovery-<project>.xlsx`,
`assessment-report.md/.docx`) are generated next to the project dir and are what people open.

Touching client data: **read-only**; service principal + OAuth M2M, no personal PATs; egress is
metadata, statistics, and ≤ 20 masked sample rows; every access recorded in `manifest.json`.

## Boundaries

Not here: detailed extraction (`requirements-extraction`), code reading (`legacy-etl-archaeology`),
matrix and report (`assessment-synthesis`), code conversion (Lakebridge), security scanning (SAT —
run it, read it), pipeline design (Databricks implementation skills), pricing (delivery lead).

## References

`references/run-layout.md` (required) · `references/project-type-*.md` (one, per Axis A) ·
`references/databricks-builtin-map.md` (before building anything Databricks may already ship).
