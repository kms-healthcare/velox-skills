# Where rules hide in DW/ETL artifacts — and how to export each

## SQL Server (T-SQL)

**Export objects** (one file per object, so anchors and Lakebridge both work):
- SSMS → Tasks → *Generate Scripts* → "one file per object", include indexes/triggers.
- Or `mssql-scripter -S <srv> -d <db> --file-per-object -f ./export/`.
- Or from the catalog: `SELECT OBJECT_SCHEMA_NAME(object_id), name, OBJECT_DEFINITION(object_id) FROM sys.objects WHERE type IN ('P','V','FN','TF','IF','TR')`.

**Where rules hide**
- `WHERE` predicates with literals; `CASE` ladders; `ISNULL/COALESCE` defaults; `TOP 1 … ORDER BY`
  tie-breaks; `MERGE … WHEN MATCHED AND …` conditions; `HAVING`; computed columns in DDL; `CHECK`
  constraints and defaults in DDL (they *are* rules); triggers (invisible logic).
- Join type: `INNER JOIN dim` = "drop unmatched" rule. `LEFT JOIN … WHERE dim.key IS NULL` = anti-join rule.
- Dynamic SQL (`EXEC(@sql)`, `sp_executesql`) — dependencies invisible to parsers; read the string builder.
- Temp tables and table variables — intermediate grain changes.
- `SET DATEFIRST`, `DATEADD(hh, 7, …)` — timezone and calendar rules.
- Linked servers (`[SRV].[db].[schema].[obj]`) — cross-system dependency.

**Scheduler (SQL Agent)** — the real DAG and runtimes:
```sql
SELECT j.name, s.step_id, s.step_name, s.subsystem, s.command, s.database_name,
       j.enabled, j.owner_sid
FROM msdb.dbo.sysjobs j JOIN msdb.dbo.sysjobsteps s ON s.job_id = j.job_id
ORDER BY j.name, s.step_id;

-- schedules
SELECT j.name, sc.name AS schedule, sc.freq_type, sc.freq_interval, sc.active_start_time
FROM msdb.dbo.sysjobs j
JOIN msdb.dbo.sysjobschedules js ON js.job_id = j.job_id
JOIN msdb.dbo.sysschedules sc ON sc.schedule_id = js.schedule_id;

-- per-step durations (run_duration is HHMMSS packed as int)
SELECT j.name, h.step_id, h.step_name, h.run_date, h.run_time, h.run_duration, h.run_status
FROM msdb.dbo.sysjobhistory h JOIN msdb.dbo.sysjobs j ON j.job_id = h.job_id
WHERE h.run_date >= CONVERT(int, FORMAT(DATEADD(day,-120,GETDATE()),'yyyyMMdd'))
ORDER BY h.run_date DESC, h.run_time DESC;
```
`freq_type = 16` (monthly) or `32` (monthly relative) → month-end jobs. `enabled = 0` → candidate `DEAD`, but check history first.

**Usage** — the only basis for `orphan`:
- Query Store (if enabled): `sys.query_store_query`, `query_store_query_text`, `query_store_runtime_stats` — persistent, best.
- `sys.dm_exec_query_stats` + `dm_exec_sql_text` — **only since the last service restart**. Always record `SELECT sqlserver_start_time FROM sys.dm_os_sys_info` in the manifest; a 6-day window proves nothing.
- `sys.dm_db_index_usage_stats` — last seek/scan/lookup per index → last read per table (also resets on restart).
- SQL Server Audit / Extended Events if configured.

**Reports (SSRS)**:
```sql
SELECT c.Path, c.Name, COUNT(*) AS exec_count_90d, MAX(e.TimeStart) AS last_exec
FROM ReportServer.dbo.ExecutionLog3 e JOIN ReportServer.dbo.Catalog c ON c.ItemID = e.ReportID
WHERE e.TimeStart >= DATEADD(day, -90, GETDATE())
GROUP BY c.Path, c.Name;
```
Zero executions in 90 days is a question, not a verdict. Report `.rdl` files: look in `<Filters>`,
`<CalculatedField>`, `<Expression>` and dataset `<CommandText>` — business exclusions often live
only here.

## SSIS (`.dtsx`)

XML. Rules hide in: `Derived Column` expressions, `Conditional Split` conditions, `Lookup`
components with *ignore/redirect/fail on no match* (a join-type rule), `Execute SQL Task`
`SqlStatementSource`, package/project **variables and expressions** (`@[User::Threshold]` →
`CONFIG-ONLY`), and `ConnectionManagers` (hard-coded credentials, server names → findings).
Precedence constraints define intra-package order. `ProtectionLevel` tells you whether secrets
are embedded.

## Informatica / DataStage

Informatica XML: `TRANSFORMATION` of type `Expression`, `Filter`, `Router`, `Lookup` (unconnected
lookups are the hidden ones), `Update Strategy` (DD_INSERT/DD_UPDATE/DD_REJECT = SCD rule),
mapping parameters (`$$PARAM` → `CONFIG-ONLY`), session-level pre/post SQL. Workflow XML for the
DAG. DataStage `.dsx`: Transformer stage derivations and constraints, Lookup stages, job
parameters, sequencer jobs for the DAG.

## Oracle / Teradata

Oracle: `DBA_SOURCE` for packages/procedures, `DBA_VIEWS.TEXT`, `DBA_TRIGGERS`, `DBA_SCHEDULER_JOBS`;
usage via AWR (`DBA_HIST_SQLSTAT`, licensed) or `V$SQL` (recent only) or audit trail.
Teradata: `SHOW PROCEDURE`, `DBC.TablesV.RequestText`, macros (`SHOW MACRO`); usage via DBQL
(`DBC.DBQLogTbl`, `DBQLObjTbl` for object-level access — ideal for orphan detection); scheduler
usually external (Control-M, TWS).

## The month-end / year-end trap

A table or job that runs only at period end is invisible in a 30-day window and usually invisible
in 60. Rules:
- Require the usage window to include **at least one month-end and one quarter-end**; 13 months is
  ideal for year-end.
- Cross-check scheduler `freq_type` for monthly/yearly jobs before calling anything orphan.
- Ask explicitly: "Which jobs run only at month, quarter, or year end?"
- `orphan: null` with an open question is the correct state until then.

## Config tables to always look at

Anything named `*CFG*`, `*PARAM*`, `*SETTING*`, `*LOOKUP*`, `*MAP*`, `*EXCLUS*`, `*RULE*`; dimension
flags (`is_active`, `include_in_report`); small tables with few rows and many readers. Get a masked
dump; record values with a locator; find the owner.

## From artifacts to inventory fields

| Inventory field | Source |
|---|---|
| `writers` / `readers` | Analyzer JSON dependencies + your reading of dynamic SQL + report `CommandText` |
| `schedule`, `run_as` | `sysjobschedules`, `sysjobs.owner_sid` / SSIS proxy / Control-M |
| `avg_runtime_min` | `sysjobhistory.run_duration` averaged over ≥ 30 runs |
| `last_read_at`, `exec_count_90d` | Query Store / DBQL / `ExecutionLog3` |
| `row_estimate`, `size_gb` | `sys.dm_db_partition_stats`, `DBA_TABLES`, `DBC.TableSizeV` |
| `pii_candidates` | Column names + sample values (masked) — never claim from names alone |
| `complexity` | Analyzer tier; do not re-score by hand |
