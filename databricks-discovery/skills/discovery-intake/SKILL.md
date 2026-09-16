---
name: discovery-intake
description: >
  The entry point for discovery and assessment on a Databricks data project — it runs before the
  requirements, legacy-code and report skills, which all follow it. Use when a project is starting
  or being sized up. Triggers: "client wants to move to Databricks", "boss asked me to evaluate
  system X", "we have 300 stored procs to understand", "where do I start", "what should I ask the
  client", "how do I estimate this", or any mention of discovery, assessment, current-state review,
  migrating a warehouse / SSIS / Informatica / Teradata / SQL Server, consolidating workspaces,
  rising cost, a new lakehouse, streaming, an ML platform, or Delta Sharing. Also when client
  documents, stored procedures or DDL arrive with no clear question. Not for writing pipelines,
  tuning queries, or operating a workspace.
compatibility: Runs outside Databricks. Python 3.9+ with openpyxl for the generator.
metadata:
  version: "0.3.0"
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

## The Iron Law

```
NO CONCLUSION WITHOUT A LOCATOR SOMEONE ELSE CAN OPEN
```

**Violating the letter of these rules is violating the spirit of these rules.** They bind every
skill in this pack. A conclusion a reviewer cannot check in five seconds is a guess in a suit.

## Three rules, never broken

1. **Do not invent.** No table, column, catalog, job, or system name that evidence has not shown;
   no number without a `locator`. Use `<catalog>.<schema>.<table>`, `<source system>` until
   verified. Invented names look real, get copied into code, and surface in front of the client.
2. **Separate "the source says" from "I infer".** Every current-state statement is `stated`
   (locator) or `inferred` (basis given, and an open question raised). Conclusions rest on `stated`.
3. **Deliver while asking.** Each turn: deliver everything that does not depend on an answer,
   then ask **≤ 5 blocking questions**, each with *why · recommended default · what breaks if wrong ·
   who to ask*. Users abandon a skill after the second interrogation. Never act past a gate in
   `references/interaction-protocol.md` without an answer, and never block the whole turn on one.

**First turn on thin input** ("client wants SQL Server → Databricks, I have some procs, where do I
start?"): classify provisionally, record input levels, propose an Axis C sentence to edit, emit the
source request, attach ≤ 5 questions. Never answer "give me more information".

## Red Flags — stop and re-check

- A table, column, catalog, job or system name in your output that no source showed you
- A number, count, percentage or date with no `locator` beside it
- About to reply "give me more information" instead of delivering the source request
- About to write a second report by hand, or copy source files into the project
- Marking a record `reviewed` or `confirmed` yourself
- Summarising the report and workbook again in the chat reply

**Every one of these means: go back to the register and the locator.**

## Rationalizations

| Excuse | Reality |
|---|---|
| "The client is in a hurry — I'll skip intake and start reading" | The hurry is why the intake exists. Thirty documents read against the wrong decision is the expensive path, not the fast one. |
| "It's obviously a migration, no need to write Axis A down" | Obvious to you. The *real driver* — licence date, the expert leaving, a CFO — is what sets scope, and it is rarely the stated one. |
| "Axis C is obvious: scope and budget" | Then it costs one sentence to write, and the sponsor can correct it before you spend the budget. Unwritten, it drifts. |
| "Five documents is enough to conclude" | Documents are L1. They describe the design, not the running system. Say what they can and cannot carry. |
| "Asking five questions again will annoy them" | Rule 3 is deliver **and** ask. What annoys people is being asked and getting nothing back. |
| "The engineer in this chat confirmed it" | That is `user-relayed`. It raises confidence; it does not close a question against a named owner. |
| "I'll summarise the report in chat so they don't have to open it" | A third copy with no locator. Keep the turn under ~300 words. |

## Cost discipline

Read `references/run-layout.md` once; load **one** project-type module; do not copy source files
(reference by path + sha256); respect the record budget in run-layout; produce **one** report — the
generator's — and write only the four author sections. Last iteration spent a quarter of its output
on a second hand-written report and 32 file copies. None of it improved the assessment.

**The reply itself is not a deliverable.** The user is about to open the report and the workbook;
summarising them in chat writes the same content a third time. Keep the turn under ~300 words:
what you concluded, what you wrote (paths), the ≤ 5 blocking questions, and what you deliberately
did not conclude. Findings, rule tables and inventory belong in the registers, where they carry a
locator and can be merged — in chat they are read once and lost.

## Interaction contract

This skill runs in a conversation; access, approval and business answers arrive there or not at all.
`references/interaction-protocol.md` is the contract — **read it before the first turn**. In short:

- **Every reply has four parts**: what I concluded · what I wrote (paths) · what I need (≤ 5
  questions, or an access request) · what I deliberately did not conclude.
- **Stop and ask before**: connecting to any client system even read-only · running a scanner on a
  live system · reading row data · egress past metadata + statistics + ≤ 20 masked rows · writing
  into `registers/` · overwriting a deliverable already sent · sending anything to anyone outside
  this chat · spending money · changing the decision or the scope. Do the work up to the gate, then
  ask in the same turn. Silence is not approval; record each granted gate in `manifest.json`
  `approvals[]`.
- **Ask for access in the eight-line block** (what · what it unlocks · minimum grant · identity ·
  who grants · lead time · what I do meanwhile · what stays out of the report if never). Access is
  the longest lead item in the project; pending two turns is a risk worth naming with a date.
- **An answer in chat is not the client's decision.** `answer_kind` is `client-confirmed` (a named
  owner, with a locator — the only kind that may set `owner_agreed` or `VERIFIED`), `user-relayed`
  (the engineer's belief; the question stays open), or `assumed-default` (nobody answered; say so
  out loud, keep the row in report §2).
- **Interrupt immediately** for a credential in client code, unexpected PII, or evidence the
  decision date cannot be met. Everything else waits for the end of the batch.

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
start, end, last restart if DMV-based). Agents fill gaps with plausible prose; this table forces
gaps to show.

This table is reproduced **verbatim as report §4**, which the sponsor reads — so write it in the
business register: "needs a measurement on the live system", not "needs profiling (L3)"; "the code
and the spec disagree", not "CONFLICT". Full label list:
`../assessment-synthesis/references/plain-language.md`.

## Step 4 — Confirmation questions → `open_questions.jsonl`

Generated from contradictions and gaps, never from a template. Weak: "how does revenue work?"
Strong: "`sp_Calc_Daily_Revenue:45-52` excludes `HCM-99` and `status = 9`; spec §4.1 mentions
neither. Still valid, and who decides?" Fields: `question · why · evidence · ask (a person) ·
default · impact_if_wrong · blocking`. ≤ 5 to the user per turn, ordered by `impact_if_wrong`.

`question` and `default` are printed unchanged in report §2, in front of the person who has to
answer. Write both in the business register — no status code, no record id as the subject. Not
"Keep 10,000; mark BR-04 CONFLICT" but "Keep 10,000, and record that the 2016 spec says 5,000 and
nobody has reconciled the two".

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
metadata, statistics, and ≤ 20 masked sample rows; every access recorded in `manifest.json`, and
every access **asked for first** — see `references/interaction-protocol.md` §2–§3.

## Boundaries

Not here: detailed extraction (`requirements-extraction`), code reading (`legacy-etl-archaeology`),
matrix and report (`assessment-synthesis`), code conversion (Lakebridge), security scanning (SAT —
run it, read it), pipeline design (Databricks implementation skills), pricing (delivery lead).

## References

`references/run-layout.md` (required) · `references/interaction-protocol.md` (required — the turn
contract, approval gates, access requests, how answers are recorded) ·
`references/project-type-*.md` (one, per Axis A) ·
`references/databricks-builtin-map.md` (before building anything Databricks may already ship).
