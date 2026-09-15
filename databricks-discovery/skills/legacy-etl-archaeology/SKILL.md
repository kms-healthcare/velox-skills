---
name: legacy-etl-archaeology
description: >
  Recover the business rules, dependencies, and inventory hidden in legacy data-warehouse and ETL
  code before migrating it to Databricks — T-SQL / PL/SQL / Teradata stored procedures, views,
  SSIS packages, Informatica and DataStage exports, SQL Agent and Control-M job definitions, SSRS
  and Cognos report logic. Produces a business-rule register with VERIFIED / CONFLICT / CODE-ONLY /
  CONFIG-ONLY / DEAD statuses, a dependency graph, and inventory records with real usage, all with
  code locators. Use when the user has legacy DW/ETL code and asks to "understand what these stored
  procedures do", "find the business rules", "what is not in the spec", "map dependencies", "which
  tables are orphan", "prepare for Lakebridge", or "the DBA is leaving and nobody knows this
  system". Works alongside Lakebridge Analyzer (inventory/complexity) and the legacy-spec-extraction
  skill (rule-register method) — it does not convert code and does not replace either.
compatibility: Runs outside Databricks. Filesystem; Python 3.9+ optional for helper scripts. Uses the legacy-spec-extraction skill's method and scripts when that skill is installed.
metadata:
  version: "0.1.0"
parent: discovery-intake
---

# Legacy ETL archaeology — what the code actually does, and what nobody wrote down

## Where this sits among the tools

Three things read legacy DW code, and they do different jobs:

| Tool | Answers | Does not answer |
|---|---|---|
| **Lakebridge Analyzer** (`databricks labs lakebridge analyze … --generate-json true`) | How many objects, of what kind, how complex, what depends on what — mechanically | What any rule *means*, whether it is documented, whether it is still wanted |
| **`legacy-spec-extraction`** skill (Velox) | The method: rule register, status taxonomy, identifier anchors, code-first-then-docs, calibration | Data-warehouse specifics: SSIS, scheduler DAGs, report-level logic, usage logs, orphan traps |
| **This skill** | Applies that method to DW/ETL artifacts, consumes Analyzer output as the inventory backbone, and emits the registers the assessment needs | Code conversion (Lakebridge Transpiler), platform design (`assessment-synthesis`) |

If `legacy-spec-extraction` is installed, **read its SKILL.md and `references/rule-register.md`
first** and use its `scripts/anchor_hash.py` for anchors. If it is not installed, the essential
method is restated below — but install it; its `extraction.md` and `tests.md` are worth having.

## The rule that matters most: code first, documents second

**Do not read documentation and code in the same pass.** With both in context the model uses the
docs to interpret the code and produces a smooth spec with no visible seams — exactly at the
places where the system drifted from its documentation. Instead:

1. Derive rules from code alone. Documents out of context.
2. Load the documents (or the `requirements.jsonl` produced by `requirements-extraction`) and diff.
3. Record every disagreement as `CONFLICT`. Never resolve it yourself.

Exception: a glossary or data dictionary may be loaded first — it maps names (`CUST_TYP_CD`), not
behaviour.

The `CONFLICT` and `CODE-ONLY` lists are the highest-value output of the whole assessment. Each
entry is a rule the business is running on without knowing it, or a rule the business believes it
has but does not. Example: `sp_Calc_Daily_Revenue` excludes `store_code = 'HCM-99'`; the 2016 spec
never mentions HCM-99. Lakebridge will transpile that predicate faithfully and nobody will ever ask
why it is there. This skill exists so that someone asks.

## Inputs

From `discovery-intake`: `intake.md`, source list. Under `sources/`:

| Artifact | What it yields | Notes |
|---|---|---|
| Exported object scripts (one file per object) | Rules, dependencies, dead code | Run Lakebridge Analyzer on this folder first; its JSON is `src-analyzer-01` |
| SSIS `.dtsx` / Informatica XML / DataStage `.dsx` / ADF JSON | Transformations *outside* the database, connection strings, hard-coded credentials, schedule hints | Expressions and derived-column components carry rules |
| Scheduler exports: `msdb.dbo.sysjobs/sysjobsteps/sysjobschedules/sysjobhistory`, Control-M XML | The real DAG, run windows, **actual durations**, run-as accounts | Job history gives per-step runtime — the critical path comes from here |
| Report definitions: SSRS `.rdl`, Cognos specs | Report-level logic (filters, calculated fields) that is in no procedure | Often the only place a business exclusion lives |
| Usage logs: Query Store, `dm_exec_query_stats`, DBQL, AWR; `ReportServer.ExecutionLog3` | Who reads what, how often — the only basis for `orphan` | Check the window covers month-end and quarter-end |
| Configuration / lookup tables (content, not just DDL) | `CONFIG-ONLY` rules — the most commonly lost class | Ask for a masked dump of small parameter tables |

## Procedure

### 0. Inventory backbone from the Analyzer

Load Lakebridge's JSON into `inventory_tables.jsonl`, `inventory_pipelines.jsonl`,
`dependency_edges.jsonl`. Every record gets `evidence.locator` = the Analyzer report row. Do not
hand-count what the Analyzer counted. Where the Analyzer's dependency extraction is incomplete
(dynamic SQL, linked servers, SSIS variables), supplement from your own reading and mark those
edges `kind: inferred`.

If no Analyzer output exists, build the inventory from the scripts — and write in `review.md`
that the Analyzer was not run and why.

### 1. Choose units

A unit is one coherent behaviour a reviewer can hold in their head: one stored procedure's core
calculation, one SSIS data flow, one report's filter set. 10–20 rules per unit; split above ~25.
Start with the units on the **critical path** and the ones behind the **most-used reports** — not
the alphabetically first procedure.

### 2. Extract rules from code (documents out of context)

For each unit, every rule gets:
- `id`, `name`, `logic` (the predicate or expression, verbatim or lightly normalised), `plain`
  (one sentence in business language — *what*, not *how*)
- `anchor` = named identifier (`dbo.sp_Calc_Daily_Revenue`, `pkg_pos_load/DFT Load Txn/Derived
  Column 1`) + content hash. **Never line numbers alone** — they are wrong after the first
  reformat, and silently so. Line numbers may appear in `source.locator` for convenience, but the
  anchor is the identifier.
- `config_driven: true` when the value comes from a table or variable rather than a literal — then
  go read that table (step 4).

Look specifically for the rule classes DW code hides best:
- **Filters that are business decisions**: `status <> 9`, `store_code <> 'HCM-99'`, `amount > 0`,
  date windows (`DATEDIFF(day, …) <= 7`).
- **Join types as rules**: an `INNER JOIN` to a dimension silently drops unmatched facts. That is a
  rule ("transactions without a known store are excluded") and usually an unintended one → also a
  `finding`.
- **Precedence and tie-breaking**: `ROW_NUMBER() … ORDER BY updated_at DESC` decides which duplicate
  wins. Business rule.
- **NULL handling**: `ISNULL(x, 0)` turns unknown into zero. Business rule with a revenue impact.
- **Currency, unit, timezone conversions** and where the rate comes from.
- **Hard-coded lists** (`IN ('A','B','C')`) — ask what the list means and who maintains it.
- **Dynamic SQL** — flag; dependencies are hidden and the Analyzer may have missed them.
- **Cursors / row-by-row loops** — not a rule, but a finding: the Databricks version will differ
  in shape, and behaviour under duplicates may differ.
- **Full rebuilds where incremental was possible** — finding with a cost/critical-path impact.

### 3. Diff against documents and assign `rule_status`

Now load `requirements.jsonl` (from `requirements-extraction`) or the documents themselves.

| Status | Meaning | Action |
|---|---|---|
| `VERIFIED` | Code and documents agree | Build it; no expert time needed |
| `CONFLICT` | Code and documents disagree | Top-priority question for a domain owner |
| `CODE-ONLY` | Code does it; no document mentions it | Usually the largest group. Needs owner review or a test to lock behaviour |
| `DOC-ONLY` | Documented, not implemented in code | Cut feature, or lives elsewhere (report filter? Excel?). Still `DOC-ONLY` when a *different* mechanism achieves a similar effect — name the substitute in `plain` and raise a question. Do not build it |
| `CONFIG-ONLY` | The rule is in configuration data, not logic | Capture the data as part of the spec; find who can change it |
| `DEAD` | Implemented but unreachable (never scheduled, never called, no readers) | Confirm with usage log, then exclude |
| `UNRESOLVED` | Needs a human who knows the business | Blocked; track the owner |

**Code wins on behaviour. Documents win on intent.** Threshold is 5,000 in the doc and 10,000 in
the code → current behaviour is 10,000; the doc says it once had a reason → `CONFLICT` and a
question, not a decision.

### 4. Read configuration data

Rules that live only in lookup tables (`CFG_PARAM`, `DIM_STORE.is_active`, exclusion lists) are
the class most often lost in migrations. For every `config_driven: true` rule, obtain the table
content (masked) and record the effective values with a locator into the dump. Note who can
change the table — that is a governance requirement.

### 5. Dependencies, critical path, and usage

- Complete `dependency_edges.jsonl` from scheduler + code. Generate the DAG (Mermaid) from the
  file, never by hand.
- From job history: per-step durations → the **critical path** and the longest serial chain. Note
  full rebuilds (`TRUNCATE` + reload of an 8M-row table nightly) as findings.
- From usage logs: `readers`, `last_read_at` per table and report. Set `orphan = true` **only** when
  the log window covers ≥ 90 days including a month-end and a quarter-end; otherwise leave
  `orphan: null` and raise a question ("year-end only?").
- **Always record the usage window in `sufficiency.md`**: source (Query Store / DBQL / DMV), window
  start and end, and — for any DMV-based source — the last service restart
  (`sqlserver_start_time`), because `dm_exec_*` and `dm_db_index_usage_stats` reset on restart. A
  usage claim without its window is not evidence.
- **`complexity` comes from the Analyzer only.** If no Analyzer output exists, leave `complexity: null`
  or, if you must triage by hand, set `complexity_source: "manual"` on the record and say so in
  `review.md` and the report. Hand-assigned tiers presented as if measured are fabrication.
- Direct consumers outside the DW (Excel/ODBC sessions, other apps) → `inventory_reports.jsonl`
  with `kind: external_consumer` and a finding if unknown to the DW team.

### 6. Findings

Anything that is not a rule but the assessment must know: silent data loss (INNER JOIN, `TRY_CAST`
to NULL), hard-coded credentials in packages, shared service accounts (`svc_etl` runs everything),
PII in plaintext, cursors on large tables, timezone-naive `DATETIME`, collation-dependent joins,
identity columns the target will not reproduce, linked-server calls.

### 7. Open questions

Every `CONFLICT`, every `CODE-ONLY` with business impact, every `CONFIG-ONLY` without a known
owner, every `orphan: null` → an `open_question` with `ask` a named role and a `default`. Order by
`impact_if_wrong`; the top 3–5 go to the user this turn.

## Calibrate before scaling

Pick one unit that **is** well documented. Extract from code alone; diff; have the client's expert
review. The correction rate is this codebase's error rate for the method. Report it in
`review.md`. If it is high, change the approach before doing 87 procedures.

## Output

`runs/<date>_run-NN/`: `business_rules.jsonl`, `inventory_*.jsonl`, `dependency_edges.jsonl`,
`findings.jsonl`, `open_questions.jsonl`, `manifest.json`, `review.md`. `review.md` leads with the
`rule_status` distribution — that distribution over time is the real progress metric, not
procedures processed.

Optionally, per unit, a Markdown unit file in the `legacy-spec-extraction` layout
(`20-rules/<unit>.md`) if the client wants a browsable spec; generate it **from** the JSONL.

## Hand-off to Lakebridge and to the assessment

- The rule register tells the **Transpiler** stage what to test: every `CODE-ONLY` and `CONFLICT`
  rule becomes a characterization test / reconciliation check.
- `inventory_*` with `readers`, `orphan`, `complexity` is what `assessment-synthesis` needs to fill
  `disposition`.
- Findings on the critical path feed the re-architecture recommendation.

## Failure modes

| Failure | Sign |
|---|---|
| Docs and code read together | Register with no `CONFLICT` rows on a 10-year-old system |
| Paraphrasing code into prose | Unit files longer than the procedure they describe |
| Line-number anchors | Anchors break on the first reformat; register rots |
| Calling orphans from a 30-day log | Month-end jobs retired; discovered in month 2 |
| Skipping config tables | Migrated logic behaves differently because a lookup value was never carried over |
| Resolving conflicts unilaterally | Confident sentence, empty `conflicts[]` |
| Alphabetical order | Two weeks on `sp_Archive_*` while `sp_Calc_Daily_Revenue` waits |

## Reference files

- `../discovery-intake/references/run-layout.md` — schemas. Required.
- `references/dw-artifact-guide.md` — where rules hide in T-SQL, SSIS, SQL Agent, SSRS; the
  system-catalog queries to export each artifact; usage-log windows and the month-end trap.
- `legacy-spec-extraction` skill (if installed): `references/rule-register.md`, `extraction.md`,
  `tests.md`, `scripts/anchor_hash.py`.
