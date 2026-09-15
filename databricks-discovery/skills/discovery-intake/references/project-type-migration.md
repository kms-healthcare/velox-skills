# Project type 1 — Migration / modernization

Load when Axis A = migration. Covers legacy data warehouses (Teradata, Oracle, SQL Server, Netezza,
Synapse, Hadoop/Hive) and legacy ETL/BI (SSIS, Informatica, DataStage, Talend, SSRS, Cognos, BO).
This is the type where discovery has the most evidence to work with — and where the most is
silently lost.

## Recognising it

Signals: "legacy", "license renewal / end of life", "vendor", a named DW product, a named ETL tool,
"the DBA is retiring", "move to the cloud", "lift and shift". Also "we already tried once" — a
previous failed migration is common and changes everything (see *Lineage* below).

## The real driver — ask before anything else

> "Why now? If nothing happens, what breaks in 12 months?"

| Stated | Usually means | What it changes |
|---|---|---|
| "License ends on date X" | Hard deadline; scope must fit the date | Rationalization becomes the main deliverable; retire aggressively |
| "It can't scale / jobs overrun" | Performance problem wearing a migration costume | Load `project-type-cost-performance.md` as secondary; re-architecting the critical path may matter more than moving everything |
| "The one person who knows it is leaving" | Knowledge risk | Business-rule extraction (`legacy-etl-archaeology`) is the critical path, not code conversion; schedule interviews **first** |
| "Board says cloud / AI" | No concrete driver yet | Push for a pilot use case (Axis C); otherwise scope = everything |
| "Cost" | Cost problem | May not justify a full migration — say so |

## Decisions this assessment typically serves (Axis C)

- **Scope**: what to migrate, modernize, retire, defer — the rationalization matrix is the centre
  of the report.
- **Waves**: order by dependency and business criticality; pick the pilot.
- **Approach per workload**: transpile as-is vs re-architect (e.g. a 14-step serial chain should
  not be reproduced as 14 serial tasks).
- **Estimate drivers**: object count × complexity × trial automation rate.
- **Go/no-go on the deadline**.

## Sources to request

### Required — the core conclusions are impossible without these

| Source | Why | How to obtain |
|---|---|---|
| **Read-only access** (service principal) to the source DB, incl. system catalogs, `msdb` / scheduler DB, report server DB | Everything below; the longest lead item | DBA creates a login; request on day one, name the deadline |
| **Full object scripts**: DDL, stored procedures, views, functions, triggers, synonyms | Inventory, business rules, dependencies | SQL Server: SSMS *Generate Scripts* one-file-per-object, or `mssql-scripter`; `sys.sql_modules`. Oracle: `DBA_SOURCE`, `DBMS_METADATA`. Teradata: `SHOW TABLE/VIEW/PROCEDURE` via BTEQ. Export into a folder tree — this is the input to Lakebridge Analyzer |
| **ETL artifacts**: SSIS `.dtsx`, Informatica XML exports, DataStage `.dsx`, Talend jobs, ADF JSON | Pipelines, schedules, hidden transformations | Export from the tool's repository; SSIS from SSISDB or the project files |
| **Scheduler definitions**: SQL Agent jobs & steps, Control-M / Autosys / cron | The real DAG and run windows; dependencies *outside* the database | `msdb.dbo.sysjobs`, `sysjobsteps`, `sysjobschedules`, `sysjobhistory` (runtimes!); scheduler exports |
| **Usage logs covering ≥ 90 days and at least one month-end and one quarter-end** | Orphan detection; who actually uses what. **Without this, nothing may be called orphan** | SQL Server: Query Store (`sys.query_store_*`) if enabled; `sys.dm_exec_query_stats` (**only since last restart — check `sqlserver_start_time`**); SQL Audit. Teradata: DBQL (`DBC.DBQLogTbl`). Oracle: AWR / `DBA_HIST_SQLSTAT`, audit trail |
| **Report inventory with execution history** | 8 of 15 reports typically have no known user | SSRS: `ReportServer.dbo.Catalog` + `ExecutionLog3`. Cognos: content store + audit DB. Power BI: activity log |
| **Row counts and sizes per table** | Volume drives estimate, backfill plan, and which "bronze" tables are actually staging | `sys.dm_db_partition_stats`; `DBA_TABLES.NUM_ROWS`; `DBC.TableSizeV` |

### Recommended

| Source | Why | How |
|---|---|---|
| Existing specs, design docs, data dictionary | Intent and identifier meanings — load **after** code (see `legacy-etl-archaeology`) | Client wiki / SharePoint; ask for the *oldest* and the *newest* |
| **UAT scripts, test plans, sample expected outputs** | The most reliable statement of behaviour that exists — literal input/output pairs. Most overlooked | QA team, old project folders |
| Tickets / change requests for the last 2–3 years | The only place that says *why* a rule changed | Jira / ServiceNow export filtered by the DW project |
| Current infrastructure and license cost | Baseline for the business case | Finance / vendor invoices |
| Report SLA and business calendar | "Revenue before 07:00", month-end close dates | Interview the report owner |
| Downstream consumer list | Systems that read the DW directly — often unknown to the DW team | Firewall / connection logs; `sys.dm_exec_sessions` sampled over days; ask "who complains when it is late?" |

### Optional

Masked sample data (≤ 20 rows/table); interview transcripts; previous migration attempt documents.

## Databricks tools to use instead of building your own

| Need | Use | Notes |
|---|---|---|
| Inventory + complexity of the exported code | **Lakebridge Analyzer**: `databricks labs lakebridge analyze --source-directory <exported-scripts> --report-file <out>.xlsx --source-tech <e.g. MSSQL, SSIS, Informatica> --generate-json true` | Free, Databricks Labs; 40+ source technologies incl. SQL Server, SSIS, SSRS, Informatica, DataStage, Teradata, Oracle, Synapse, Snowflake, Talend, ADF. Input is the folder of exported SQL / XML / JSON metadata. Output is an `.xlsx` report (and `.json` with the flag — **use the JSON as the agent's input**) covering programs, transformations, functions, dynamic variables, complexity and interdependencies. Register it as `src-analyzer-01`; load into `inventory_*.jsonl` and `dependency_edges.jsonl` |
| Trial conversion to measure the automation rate | **Lakebridge Transpiler** on a sample of 10–20 objects across complexity tiers | Do this *during* assessment — the measured rate is the only honest estimate driver |
| Post-migration data validation | **Lakebridge Reconcile** | Not a discovery task, but its existence shapes the acceptance criteria you write |
| Ingesting from SQL Server / SaaS after migration | **Lakeflow Connect** (managed CDC connectors) | Affects the source-spec questions: is CDC / Change Tracking enabled at the source? |
| Target semantic layer | **Unity Catalog metric views** | Business rules that are *metric definitions* should land here, not in ten Gold tables |

What none of these do: extract business rules in business language, flag rules that are absent
from the spec, or decide what to retire. That is `legacy-etl-archaeology` and `assessment-synthesis`.

## Conclusions the report must reach

1. **Inventory with usage** — tables, pipelines, reports; each with readers/writers, last used,
   volume. From scanner output, not from the spec.
2. **Rationalization matrix** — every object gets `migrate | modernize | retire | defer` with the
   evidence. Retire is where the savings are; be prepared to defend each one.
3. **Complexity distribution** and the **trial automation rate** → estimate drivers (not a price).
4. **Business rules with status** — the CODE-ONLY and CONFLICT lists are what the client is paying
   for. Each one is a question with a named owner.
5. **Dependency graph and critical path** — e.g. "14 serial steps, 5.5 h; step 9 rebuilds 8M
   customers nightly for 50k changes". This is where re-architecture beats transpilation.
6. **Consumers** — every report and downstream system, with real usage. Unknown consumer = risk row.
7. **PII exposure and access** — plaintext identifiers, shared service accounts. Feed SAT-style
   findings into `SEC-` requirements.
8. **Waves and pilot** — pilot = a business-important report with moderate complexity and clean
   dependencies, not the easiest table.

## Evidence-sufficiency rules specific to migration

| Cannot claim | Without |
|---|---|
| "X% of tables are orphan" | Usage log ≥ 90 days **including month-end and quarter-end** |
| "Effort ≈ N" | Complexity per object **and** a trial transpile on a sample |
| "Rule R is current behaviour" | A code locator; and it stays `inferred` on *intent* until a business owner confirms |
| "The nightly window can shrink to 1.5 h" | Current per-step runtimes from job history, not from the design doc |
| "Report R has no users" | Report-server execution log; absence in a 30-day window is not evidence |

## Confirmation questions that this type generates

- "These 14 reports show zero executions in 90 days (locator). Retire, or are they year-end only?"
- "This rule exists in code, not in the spec (locator). Still valid? Since when? Who owns it?"
- "Who or what reads the warehouse directly besides these reports — Excel, Access, another app?"
- "Has this system been migrated before? What changed then, and is that documented?"
- "How deep must history go on the new platform, and does the source still have it?"
- "Is there a freeze period (month-end close, audit) that constrains cut-over?"
- "Parallel run: how long, who signs off, and what tolerance for differences?"
- "Which jobs run only at month / quarter / year end?" — ask **before** calling anything orphan.

## What is routinely missed

- **Month-end / year-end jobs** look orphan in a 30-day log. Always extend the window.
- **Direct consumers**: Excel via ODBC, Access, other applications, a vendor pulling extracts.
- **Shadow ETL** in Excel/Access that sits *between* the warehouse and the report.
- **Report-level logic**: SSRS expressions and Cognos calculations contain business rules that are in
  no stored procedure.
- **Configuration tables** driving logic (`CONFIG-ONLY` rules) — the most commonly lost class.
- **Linked servers / cross-database calls** — dependencies the scripts do not show.
- **Type and semantics drift**: collation, timezone of `DATETIME`, decimal precision, `NULL` vs empty
  string, identity/sequence behaviour, implicit conversions.
- **Hard-coded credentials and shared service accounts** in packages.
- **Scheduler dependencies outside the DB** (Control-M) that define the real DAG.
- **The previous failed migration** — its documents and its silent behaviour changes.

## Cost-risk flags to raise early

| Client asks for | Why it is expensive | Breaker question |
|---|---|---|
| Lift-and-shift the serial chain as-is | Reproduces the 5.5 h window on compute billed by the second | "Which steps actually depend on each other?" |
| Migrate all 340 tables | 112 are unused; each costs conversion, testing, and maintenance | "Show me who read this table in the last quarter" |
| Full history | Backfill is a sub-project with its own cost and reconciliation | "How far back do analyses actually go? Detail or aggregate before that?" |
| Size clusters like the old server | Old sizing was for 24/7 shared hardware | "What is the run window, and can it run on job compute that stops?" |
| Keep every report | 8 of 15 have no known user | "Who complains if this report disappears for a month?" |
