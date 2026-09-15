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
compatibility: Runs outside Databricks (Claude Code or equivalent agent). Databricks CLI + managed MCP are optional for reading metadata; not required.
metadata:
  version: "0.1.0"
  audience: engineers who also own requirements on data projects
---

# Discovery intake — the entry point for every assessment

## Why this skill exists

Assessments fail in one very consistent way: someone receives a pile of documents, fills in every
section of a report template, and the report describes everything but **helps nobody decide
anything**. The cause is not writing skill. It is three things left unsettled before work starts:
*what kind of project this actually is*, *what we have in hand to conclude from*, and *who will use
the conclusion to decide what*.

This skill settles those three, then allows work to proceed. It is the spine; the specialist work
lives in the three skills it hands off to: `requirements-extraction`, `legacy-etl-archaeology`,
`assessment-synthesis`.

The user is an engineer who also owns requirements. They do not lack technical skill — they lack
**the discipline to stop and ask before building**. The skill is written for that: no lecture on
medallion, no SQL tutorial; plain statements of what must be asked, what must be requested, and what
cannot yet be concluded.

## Output language

Write every artifact in the language the user is working in. Keep object names (tables, columns,
procedures, jobs, systems) verbatim as they appear in the source — never translate identifiers.

## Three rules that are never broken

**1. Do not invent.** Never name a table, column, catalog, job, or system that has not been seen in
evidence. Never write a number (row count, object count, cost, SLA) without a `locator` pointing to
its source. Until then use placeholders — `<catalog>.<schema>.<table>`, `<source system>` — and say
what is being waited for. Invented names look real, get copied into the report and then into code,
and nobody notices until a pipeline fails or the client spots it in the readout.

**2. Separate "the source says" from "I infer".** Every statement about the current state carries
one of two labels: `stated` (with a locator into a document, code, or transcript) or `inferred`
(derived, with the basis given). Conclusions in the assessment are built only on `stated`; every
`inferred` becomes a confirmation question. This is the only line between an assessment and a
fluent essay.

**3. Deliver while asking.** Never stop to ask fifteen questions and deliver nothing. Each turn:
deliver everything that does not depend on an answer (draft intake, source request, provisional
classification), then ask **at most 3–5 blocking questions**, each with *why it matters · the
default I recommend · what breaks if wrong · who to ask*. Users pick from options far faster than
they compose answers, and they abandon a skill after the second interrogation.

## Working with a user who gives very little

The typical input is one sentence: *"client wants to migrate SQL Server to Databricks, I have some
stored proc files, where do I start?"* Do not answer "give me more information". Do this instead:
- Classify provisionally on Axis A from that sentence, **saying clearly it is provisional**.
- Record the input level on Axis B from what was mentioned.
- Propose a decision sentence for Axis C for them to edit — editing is easier than writing.
- Generate the source request for that project type.
- Attach 3–5 blocking questions.

The user gets a useful page on the first turn, and every assumption is labelled.

---

# Step 1 — Three-axis intake

Three independent axes. The same project type with a different input level or a different decision
to serve is a different problem. Skip an axis and the assessment fails in exactly that axis's way.

## Axis A — Project type, recognised through the real driver

**Do not ask "what kind of project is this".** The user answers with a solution name ("migration")
while the real driver is cost or a person about to retire. Ask for the driver, then classify and
confirm:

> "Why do this **now**? If nothing is done, what happens in 12 months?"

| Type | Signals in what the user says | The real driver usually is | Module |
|---|---|---|---|
| 1. Migration / modernization | "legacy", "license ending", "Teradata/Oracle/SQL Server/SSIS/Informatica", "move to" | license cost, cannot scale, the one person who understands it is leaving, vendor pressure | `references/project-type-migration.md` |
| 2. Greenfield lakehouse | "nothing central", "every team has its own Excel", "we want a data platform" | one concrete use case is stuck, or pressure to "have AI" | `references/project-type-greenfield.md` |
| 3. Platform / consolidation | "many workspaces", "merger", "don't know who uses what", "permissions are a mess" | duplicated cost, audit/compliance, loss of control after M&A | `references/project-type-consolidation.md` |
| 4. Cost & performance | "bill is rising", "jobs overrun their window", "dashboards are slow" | budget cut, SLA broken, CFO asking | `references/project-type-cost-performance.md` |
| 5. Real-time / streaming | "real-time", "within minutes", "Kafka", "events" | an operational decision that needs fast reaction — or just a wish | `references/project-type-streaming.md` |
| 6. ML / AI platform | "models stuck in notebooks", "GenAI on company data", "RAG", "agents" | cannot get models to production, or leadership pressure for AI | `references/project-type-ml-ai.md` |
| 7. Data sharing | "share with partners", "sell data", "Delta Sharing", "clean room" | a new contract, a partner requirement, monetization | `references/project-type-sharing.md` |

Classification rules:
- **Two types heard** (very common: migration + cost) → the one matching the real driver is
  primary, the other is `secondary`. Load both modules; deliverables and the decision follow the
  primary.
- Stated driver does not match the type → that is the assessment's first finding; write it to
  `findings`. Example: "migration" requested, but the driver is "the Teradata bill" → this is a
  cost problem, and the answer may not be migrating everything.
- Cannot classify after two rounds → record `unknown`, run the migration module as the default
  (broadest coverage), and make this blocking question #1.

## Axis B — What inputs exist

Determines what the agent **can** conclude. This is the most-skipped axis, and skipping it is the
direct cause of invention.

| Level | What exists | Can conclude | CANNOT conclude — say so plainly |
|---|---|---|---|
| L0 | Only what the user tells you | Provisional type, source request, questions | Any number; any judgement about data quality or complexity |
| L1 | Documents: specs, decks, tickets, minutes, transcripts | `stated` requirements, glossary, stakeholders, goals | The actual current state — documents describe the system *as designed*, not *as running* |
| L2 | Code / DDL / ETL artifacts: stored procs, SSIS, Informatica XML, SQL, DAGs | Running business rules, dependencies, complexity, doc-vs-code conflicts | Volume, frequency, who uses what, data quality — code cannot tell you what the data looks like |
| L3 | Access to the source system, or output of a scanner (Lakebridge Analyzer, system catalog, query logs) | Full inventory, real usage, orphans, volume, frequency | Business meaning, keep/drop decisions — those need people |
| L4 | What already exists on Databricks: Unity Catalog, system tables, workspace | Cost baseline, usage, lineage, security posture (via SAT) | What *should* exist — still needs Axis C |

Record the highest level available **per source system**, not one level for the whole project.
Very often: L3 for the main system, L0 for three side systems the client "forgot" to mention.

At L0–L1, every current-state section of the report must read *"no evidence yet — needs [source]"*.
Do not fill it with inference, however reasonable the inference is.

## Axis C — Which decision, decided by whom

An assessment is a decision instrument, not a description. Write **one sentence** and let the user
edit it:

> "This report is for **[who]** to decide **[what]** before **[when]**."

Typical decisions, and what each demands differently:

| Decision | The report must conclude | If this axis is not pinned |
|---|---|---|
| Go / no-go | Feasibility, blocking risks, prerequisites | 60 pages, and leadership asks "so do we do it or not?" |
| Scope & priority | Rationalization matrix: migrate / modernize / retire / defer | Scope = "everything", and the project balloons in week one |
| Budget / estimate | Effort drivers (object count × complexity × automation rate), compute cost baseline | Estimate from gut feel, off by 3x |
| Architecture / pattern choice | Options compared with the price of each | Architect picks by habit, nobody sees the trade-off |
| Tool / vendor choice | Criteria and scores | Chosen from the demo |

If this axis is missing, ask directly: *"After reading the report, what will you or the client do
differently?"* No action → there is no reason to do the assessment yet, and that must be said to
the user.

## Output of Step 1

`intake.md` per the template in `references/run-layout.md`. Every field labelled `stated` /
`inferred` / `assumed`. Present it for the user to edit **before** Step 2 — but attach a draft of
Step 2 in the same turn, because the source request cannot wait.

---

# Step 2 — Source request by project type

Load the primary type's module (and the secondary's, if any). Each module has a source table in
three tiers: **required** (without it the core conclusion cannot be reached), **recommended**
(materially raises confidence), **optional**. Each row carries *why it is needed* and *how to
obtain it* — clients do not hand over what they do not understand the need for, and an engineer who
does not know the export procedure asks three times.

Output: `source_request.md` — a list that can be sent to the client as-is, grouped by tier, with
the client-side owner where known. For each source **already in hand** mark it received with a
locator; for each **required source still missing** state which conclusion will be absent.

Two principles for every type:
- **Prefer scanner output over human-written documents.** Lakebridge Analyzer, SAT, query history
  and system tables describe the system *as it runs*; documents describe the system *as designed*
  in some year. When both exist, the tool is evidence and the document is intent.
- **Request access on day one.** It is the longest lead item in discovery — typically 1–2 weeks for
  a read-only service principal. Make it the first line of the source request, not the last.

---

# Step 3 — Evidence-sufficiency gate

Before writing any conclusion, build `sufficiency.md`:

| Conclusion needed (from Axis C) | Evidence required | In hand (locator) | State |
|---|---|---|---|
| e.g. "230 of 340 tables need migrating" | inventory + usage/dependency | `lakebridge/analyzer_out.xlsx` sheet Objects; `dependency_edges.jsonl` | ✅ sufficient |
| e.g. "effort ≈ X person-months" | complexity per object + automation rate | complexity in hand; automation rate **not yet trialled** | ⚠️ partial — give a range, not a number |
| e.g. "current revenue rule" | code + business confirmation | code in hand (`sp_Calc_Daily_Revenue`); business **not confirmed** | ⚠️ `stated` from code, `inferred` on intent |
| e.g. "POS data quality" | profiling on real data | **no access yet** | ❌ insufficient — needs L3 |

Rules:
- ❌ → that report section is exactly one sentence: *"Insufficient evidence. Needs [source]. Risk
  if skipped: [what]."* Write nothing more.
- ⚠️ → give a **range** or a **condition**, never a point value. State what is being assumed.
- The table goes into the report appendix. It protects the author under challenge, and it is what
  makes the client trust the rest.

This gate is the single biggest difference between an agent-assisted assessment and an invented
one: agents are very good at filling gaps with plausible prose. The table forces the gaps to show.

---

# Step 4 — Confirmation questions

Questions are **generated from the contradictions and gaps found**, not from a template. A good
question points at a specific piece of evidence:

- Weak: "How does your revenue calculation work?"
- Strong: "`sp_Calc_Daily_Revenue` lines 45–52 exclude store `HCM-99` and `status = 9`; the 2016
  spec §4.1 mentions neither. Are both rules still valid, and who decides?"

The second gets the business rule, the system history, and the decision-maker in one ask. That is
why extraction precedes interviews — bring evidence into the room, not open questions.

Record in `open_questions.jsonl` (schema in `references/run-layout.md`): `question`, `why`,
`evidence` (locator), `ask` (a person, not a department), `default` (what happens if nobody
answers), `impact_if_wrong`, `blocking` (which requirement/finding waits on it), `status`.

Send the user **at most 3–5 blocking questions per turn**. Non-blocking questions go to the register,
not to the user. Order by `impact_if_wrong`, not by order of discovery.

Each project-type module carries a characteristic question set — those are *prompts for spotting
gaps*, not a list to read to the client.

---

# Step 5 — Hand-off

| In hand | Hand to | It returns |
|---|---|---|
| Documents, transcripts, tickets, specs (L1) | `requirements-extraction` | `requirements.jsonl`, `findings.jsonl`, `open_questions.jsonl` |
| Stored procs, SSIS, SQL, DAGs, ETL XML (L2) | `legacy-etl-archaeology` | `business_rules.jsonl` with VERIFIED / CONFLICT / CODE-ONLY… status, `dependency_edges.jsonl`, `inventory_*.jsonl` |
| Scanner output: Lakebridge Analyzer, SAT, system tables (L3–L4) | the project-type module — it says how to read them | `inventory_*.jsonl`, `findings.jsonl` |
| Registers sufficient per the Step 3 gate | `assessment-synthesis` | rationalization matrix, `assessment-report.md`, estimate drivers |

Hand-off does not end the work here: after each child skill returns, come back to Step 3 to update
`sufficiency.md` and to Step 4 to add questions. Discovery is a loop, not a line.

---

# Directory layout and how the agent returns results

The agent **never writes directly into the main registers**. Each run emits a batch under `runs/`;
a person reviews `review.md`, edits the JSONL, then merges. This preserves "what the agent
proposed, what the human changed" — an audit trail and, later, the data for measuring where the
agent is wrong.

```
discovery/<project>/
├── intake.md
├── source_request.md
├── sufficiency.md
├── sources/                      # only originals that may move (emails, chat exports); files already on disk
│                                 # are referenced by path + sha256 in manifest.json, never duplicated
├── registers/                    # source of truth — only humans merge here
│   ├── requirements.jsonl
│   ├── business_rules.jsonl
│   ├── inventory_tables.jsonl
│   ├── inventory_pipelines.jsonl
│   ├── inventory_reports.jsonl
│   ├── dependency_edges.jsonl
│   ├── findings.jsonl
│   └── open_questions.jsonl
└── runs/
    └── 2026-09-14_run-07/
        ├── manifest.json         # sources read, model, skill version, counts
        ├── *.jsonl               # new / changed records only
        └── review.md             # one page for the reviewer
```

Per-file schemas and templates for `intake.md` / `review.md` / `manifest.json`:
`references/run-layout.md`. Every record links by `id`, so it is always possible to answer "where
did this requirement come from, which tables does it touch, what is still unresolved".

---

# Constraints when touching client data

These live **inside the skill**, not in the user's head — otherwise the skill will tell an engineer
to run `SELECT *` on the client's data.

- **Read-only.** All access to the client's source systems or Databricks is read-only. Any write
  (including temp tables) requires explicit user confirmation and is recorded in `manifest.json`.
- **Authenticate with a service principal + OAuth M2M** (`DATABRICKS_HOST` / `CLIENT_ID` /
  `CLIENT_SECRET`). No personal PATs. The agent never sees the secret.
- **Egress is metadata and statistics only.** What leaves the client environment: schemas, row
  counts, cardinality, null rates, top-N values of code columns, and **≤ 20 sample rows with PII
  columns masked**. Never pull a table out "to look at it". Heavy work is pushed into the workspace;
  only summaries come back.
- **Record in `manifest.json`** everything read and everything executed. This is what allows
  running on real client data with the client's consent.

---

# Common failures and their early signs

| Failure | Early sign |
|---|---|
| Classifying by solution name, not driver | A migration report for a client who only cares about the bill |
| Skipping Axis B, concluding at L0–L1 as if L3 | Row counts and complexity in the report; nothing in `sources/` but PDFs |
| Skipping Axis C | No "decision required" section; leadership reads it and asks "so what?" |
| Trusting documents over scanner output | Inventory taken from the 2016 spec while the Lakebridge output sits unopened |
| Template questions | 40 questions, none pointing at a locator |
| Agent writing straight into registers | No `runs/`; nobody knows which records a human reviewed |
| Requesting access in week 2 | Week 3 still on documents; deadline week 4 |
| Asking "what kind of system" instead of "why now" | You get a product name, not a driver |

---

# Boundaries — not done here

| Not done | Hand to |
|---|---|
| Detailed requirements extraction from documents | `requirements-extraction` |
| Reading legacy code, extracting business rules, dependencies | `legacy-etl-archaeology` (builds on `legacy-spec-extraction` when installed) |
| Rationalization matrix, estimate drivers, report writing | `assessment-synthesis` |
| Converting code to Databricks | Lakebridge Converter — not discovery work |
| Scanning workspace security configuration | SAT (Security Analysis Tool) — run it, read its output, do not rebuild it |
| Designing pipelines, writing notebooks, deploying bundles | Databricks implementation skills (`databricks-pipelines`, `databricks-dabs`, …) |
| Estimating in currency | Delivery lead, using the drivers `assessment-synthesis` supplies |

---

# Reference files

| File | Read when |
|---|---|
| `references/run-layout.md` | Before writing any file — register schemas, templates for `intake.md`, `review.md`, `manifest.json` |
| `references/project-type-migration.md` | Axis A = migration / modernization |
| `references/project-type-greenfield.md` | Axis A = greenfield lakehouse |
| `references/project-type-consolidation.md` | Axis A = platform / consolidation |
| `references/project-type-cost-performance.md` | Axis A = cost & performance |
| `references/project-type-streaming.md` | Axis A = real-time / streaming |
| `references/project-type-ml-ai.md` | Axis A = ML / AI platform |
| `references/project-type-sharing.md` | Axis A = data sharing |
| `references/databricks-builtin-map.md` | Before building anything yourself — check whether Databricks already ships a tool for it |
