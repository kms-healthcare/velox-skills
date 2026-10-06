---
name: discovery-intake
description: "Entry point for discovery and assessment on a Databricks data project: classify the project type, inventory the evidence that exists, pin down the decision the assessment must serve, then emit a source request list, an evidence-sufficiency gate, and confirmation questions before handing off to requirements extraction, legacy code archaeology, or report synthesis. Use when a user starts a data or Databricks project, or mentions discovery, assessment, current-state review, evaluating or migrating a legacy warehouse (SSIS, Informatica, Teradata, SQL Server), workspace consolidation, or rising Databricks cost - including phrasings like 'client wants to move to Databricks' or '300 stored procs to understand'. Not for writing pipelines, deploying bundles, or tuning queries."
compatibility: "Runs outside Databricks (Claude Code, Velox or equivalent). Databricks CLI + managed MCP optional. Python 3.9+ and openpyxl for the deliverables generator; pandoc optional for .docx."
metadata:
  version: "0.5.1"
---

# Discovery intake — the entry point for every assessment

Assessments fail one way: someone fills every section of a template and the result describes
everything but **helps nobody decide anything**. Three things were never settled: *what kind of
project this is*, *what evidence exists*, *who decides what with the result*. This skill settles
them, then hands off to `requirements-extraction`, `legacy-etl-archaeology`, `assessment-synthesis`.

No lectures: plain statements of what to ask, what to request, what cannot yet be concluded.
Artifacts in the user's language; identifiers verbatim.

## Three rules, never broken

1. **Do not invent.** No table, column, catalog, job, or system name that evidence has not shown;
   no number without a `locator`. Use `<catalog>.<schema>.<table>`, `<source system>` until
   verified. Invented names look real, get copied into code, and surface in front of the client.
2. **Separate "the source says" from "I infer".** Every current-state statement is `stated`
   (locator), `reproduced` (observed by running it on sample data — the strongest for behaviour),
   or `inferred` (basis given, and an open question raised). Conclusions rest on `stated` or
   `reproduced`.
3. **Deliver while asking.** Each turn: deliver everything that does not depend on an answer,
   then ask **≤ 5 blocking questions**, each with *why · recommended default · what breaks if wrong ·
   who to ask*. Users abandon a skill after the second interrogation.

**First turn on thin input** ("client wants SQL Server → Databricks, I have some procs, where do I
start?"): the deliverable is the proposal, in the reply — the provisional type and input levels, an
Axis C sentence to edit, what to request and why, ≤ 5 questions. Write `intake.md` and the source
request once the user confirms the scope and the Axis C sentence — an agent that runs an agreement
step (Velox does) runs this skill after it. Never answer "give me more information".

**The approach question has two fixed options, always, in this order** — the person's answer is
*how the assessment reads the estate*, and it must not change wording from run to run (measured
2026-10-05/06: four runs, four different option sets — "Full code + docs", "Code-based now",
"Code + docs, workspace checks added"… — so no two assessments were comparable):

1. **With the Databricks workspace** — connect it (read-only service principal by default; the
   card opens from this choice) and read code + docs + the live workspace: Unity Catalog, system
   tables, security posture scored. *Recommended whenever a workspace exists or is one click away.*
2. **Without a workspace** — code + docs only: registers, findings, readiness; security posture
   from infrastructure code only, reported as not scored, with the workspace as the first open item.
   *For pre-sales, or when the client has not granted access yet.*

A third option is allowed only when the project genuinely has another shape (e.g. "scanner output
only", when Lakebridge/UCX exports were handed over and there is no code); never a fourth. Say in
one line what each costs the person. Option 1 chosen → call `request_databricks_workspace` at once
and build the plan on the card's outcome; "I don't have a workspace yet" on the card falls back to
option 2 without asking again. Option 2 chosen → do not ask for a workspace later in the run; note
it in `source_request.md` line 1 as ❌ none yet (OQ-xx).

**The approach card carries the question and the two options — nothing else.** One line of
question ("How should the assessment read the estate?"), the options with their cost, done. No
tour of the deliverables in the preamble (they are the same either way — six words, not sixty),
and no second question folded in: "also answer the three questions above in the free-text box"
turns a click into a non-answer, and "above" is off-screen. The intake's ≤ 5 blocking questions
are their OWN card, asked after the approach is chosen — or, when a default is honest, taken as
the default and raised as `OQ-` records with `default` filled, which is what Rule 3 means by
*deliver while asking*. Security from code reads as "from infrastructure code", not a tool name
(Terraform today, bundles or Bicep elsewhere). Reviewed live 2026-10-06: a card that got the two
options right still ran 90 words of deliverables and asked three intake questions in the same box.

## Blocked mid-run — offer options, never decide alone

Every skill in this pack works one loop: **propose the plan → the person accepts → run everything
you can with the access you already have → when blocked, hand off with options.** Do not ask before
the first attempt; do not stop at the first refusal either.

Blocked means the next step needs something only the person (or their client) may give: more
access, an input you cannot reach, a cost, or a risk. Then use the session's question tool (Velox:
`ask_user`) — not prose — with:

- **2–4 options**, one marked *recommended*, each saying what it costs the person (a sign-in, a
  message to the client, a file round-trip, a gap left in the report). Always include the
  cheapest honest one — usually "skip, and say so in the report".
- **The recommendation from evidence you checked**, not habit (e.g. their login *is* an admin for
  this host). Hide an option that cannot work, and say why.
- **Nothing riskier than the bound identity without the answer** — no other login, no elevated
  grant, no write. A choice the person did not make is not theirs to defend to the client.

After the chosen path runs, **check what it left behind and warn rather than block**: a risk that
remains (a grant not revoked, a source read under someone else's login) becomes a finding with a
locator, and the deliverable is still produced — the reviewer decides. Worked example:
`security-posture` (bound read-only service principal first; under half the catalog readable →
*own login for this step* · *client grants admin briefly* · *client's admin runs the bundle* ·
*skip*; a grant still in place → a high finding).

## Cost discipline

Read `references/run-layout.md` once; load **one** project-type module; do not copy source files
(reference by path + sha256); respect the record budget in run-layout; produce **one** report — the
generator's — and write only the five author sections.

**The reply itself is not a deliverable.** The user is about to open the report and the workbook;
summarising them in chat writes the same content a third time. Keep the turn under ~300 words:
what you concluded, what you wrote (paths), the ≤ 5 blocking questions, and what you deliberately
did not conclude. Findings, rule tables and inventory belong in the registers, where they carry a
locator and can be merged — in chat they are read once and lost.

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
| L2 | code / DDL / ETL artifacts / application code (services, APIs, dashboards) | running rules, dependencies, complexity, doc-vs-code conflicts, every place data lives or leaves | volume, usage, data quality |
| L3 | source access or scanner output (Lakebridge Analyzer, catalogs, query logs) | inventory, real usage, orphans, volume | business meaning, keep/drop |
| L4 | Unity Catalog, system tables, workspace | cost baseline, lineage, security posture (`security-posture`; SAT results) | what *should* exist — Axis C |

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

"Request access" is an ACTION, not a line in a table. When the module lists a Databricks workspace
as a source (the migration target, the estate being consolidated) and none is bound to the session,
ask for it now through the session's tool (Velox: `request_databricks_workspace` — the card lets
the person connect one, as a read-only service principal by default, or say they have none yet).
Record the outcome on line 1 of `source_request.md` (✅ bound as <identity> · ❌ none yet, OQ-xx).
Measured 2026-10-05: two full assessments of the same project — one with a saved workspace one
click away — never asked, and both ended with "security: not scored, needs a workspace".

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
| application code — services, buses, APIs, dashboards (L2) | `legacy-etl-archaeology` with `references/app-estate-guide.md` — the data-surface inventory and the serving layer are in scope | `inventory` (every store, endpoint and view), `business_rules`, `findings` |
| scanner output (L3–L4) | the type module says how to read it | `inventory`, `findings` |
| a connected workspace (L4) | `databricks-unity-catalog` (catalog, lineage, system tables) and `databricks-dbsql` (queries) — Databricks' own agent skills, when listed; otherwise read `system.*` and `information_schema` directly, read-only | `inventory`, `findings` |
| registers pass the gate | `assessment-synthesis` | `rationalization`, workbook, report |

After each return, update `sufficiency.md` and the question list. Discovery is a loop.

## Layout, review, and client-data constraints

`discovery/<project>/` per `references/run-layout.md`. The agent writes only into `runs/<run>/`;
a human reviews `review.md` and merges into `registers/`. Deliverables (`discovery-<project>.xlsx`,
`assessment-report.md/.docx`) are generated next to the project dir and are what people open.

Touching client data: **read-only**; service principal + OAuth M2M, no personal PATs; egress is
metadata, statistics, and ≤ 20 masked sample rows; every access recorded in `manifest.json`.

## Related skills and boundaries

Not here: detailed extraction (`requirements-extraction`), code reading (`legacy-etl-archaeology`),
matrix and report (`assessment-synthesis`), code conversion (Lakebridge), security posture
(`security-posture` — SAT's checklist, read-only, or SAT's own results), pipeline design (Databricks' own agent skills when listed — `databricks-pipelines`,
`databricks-jobs`, `databricks-dabs`, `databricks-serverless-migration`), pricing (delivery lead).
Build on those skills by name and say which one you used; this pack covers what they do not —
evidence before the lakehouse exists, traceable registers, the client-facing report.

## References

`references/run-layout.md` (required) · `references/project-type-*.md` (one, per Axis A) ·
`references/databricks-builtin-map.md` (before building anything Databricks may already ship).
