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

## Azure Synapse (dedicated SQL pool + workspace artefacts)

T-SQL rules: the SQL Server section applies; below are the differences, and the workspace
artefacts that play the roles of SSIS and SQL Agent. Lakebridge: `--source-tech "Synapse"`.

**Export the pool's objects** — SSMS *Generate Scripts* works against a dedicated pool;
`sys.sql_modules` holds procedures and views. The DDL carries decisions the plan needs:
`WITH (DISTRIBUTION = HASH(col) | ROUND_ROBIN | REPLICATE, CLUSTERED COLUMNSTORE INDEX | HEAP,
PARTITION (col RANGE RIGHT FOR VALUES (…)))` — record the hash column and the partition column on
the inventory record; the migration's clustering follows them. When the scripts are missing,
the size query below carries the distribution.

**Where rules hide, beyond T-SQL**
- `PRIMARY KEY` / `UNIQUE` exist only as `NONCLUSTERED NOT ENFORCED`: a constraint that enforces
  nothing. Duplicates the documents say cannot exist may exist — a finding, and a reconciliation
  check for every table that carries one. No foreign keys, no triggers, no computed columns: the
  rules they would hold live in the loading procedures instead.
- `MERGE` arrived late (2022): upserts are a `DELETE` or `UPDATE` followed by an `INSERT` — one rule
  split across two statements, often with a different predicate on each half.
- **CTAS** (`CREATE TABLE … AS SELECT`) then `RENAME OBJECT` = a full rebuild with a swap;
  `ALTER TABLE … SWITCH PARTITION` = a partition-level reload. Both are the critical-path shape.
- `CREATE EXTERNAL TABLE` + `EXTERNAL DATA SOURCE` + `EXTERNAL FILE FORMAT` (PolyBase) and `COPY INTO`
  are the ingestion edges from ADLS: `file_dataset` → `table`, with the path and the format.
- `OPTION (LABEL = '…')` on statements: the label is what the request history shows — the way to
  tie a request back to the pipeline that ran it.

**Workspace artefacts** — in the workspace's Git repository (Synapse Studio → Manage → Git
configuration; `az synapse workspace show` names it) as one JSON file per object:
`pipeline/`, `dataset/`, `linkedService/`, `trigger/`, `notebook/`, `sqlscript/`, `dataflow/`,
`sparkJobDefinition/`, `integrationRuntime/`. A workspace in **live mode** has no repository:
export first, into the same folder names —
```bash
az synapse pipeline list       --workspace-name <ws> -o json > pipeline/_all.json
az synapse trigger list        --workspace-name <ws> -o json > trigger/_all.json
az synapse linked-service list --workspace-name <ws> -o json > linkedService/_all.json
az synapse dataset list        --workspace-name <ws> -o json > dataset/_all.json
az synapse notebook export     --workspace-name <ws> --output-folder notebook/
az synapse sql-script export   --workspace-name <ws> --output-folder sqlscript/
```
Register the export as a source with the date; the live workspace may have moved since.

- **Pipelines** (`pipeline/*.json`, `properties.activities[]`): `SqlPoolStoredProcedure` →
  `procedure` edge; `SynapseNotebook` → `notebook` edge (with `parameters`); `Copy` — rules hide in
  `source.sqlReaderQuery`, `sink.preCopyScript` and the column `translator`; `Script` and `Lookup`
  carry inline SQL; `ExecutePipeline` = pipeline → pipeline edge; `ExecuteDataFlow` → `dataflow/`.
  `activities[].dependsOn` is the DAG inside a pipeline; `ForEach` / `IfCondition` /
  `Switch` hold rules in their `expression`. `@pipeline().parameters.x`, `@concat(…)`,
  `@formatDateTime(…)` are the dynamic SQL of this estate — read the expression, not the type.
- **Triggers** (`trigger/*.json`): `ScheduleTrigger` (`recurrence`: frequency, interval, hours,
  minutes, `monthDays` — `-1` is the last day), `TumblingWindowTrigger` (window + `dependsOn` other
  windows = a cross-pipeline edge), `BlobEventsTrigger` / `CustomEventsTrigger` (event-driven: no
  schedule, record the path pattern). `runtimeState: "Stopped"` → candidate `DEAD`, check the runs.
  `pipelines[].pipelineReference` is the schedule → pipeline edge. A pipeline no trigger and no
  `ExecutePipeline` names is run by hand or by something outside the workspace: open question.
- **Linked services** (`linkedService/*.json`, `properties.type`): `AzureSqlDW` (the pool),
  `AzureBlobFS` (ADLS Gen2), `SqlServer`, `Oracle`, `SapTable`, `RestService`, `AzureKeyVault` —
  each is a `source_systems` record. `typeProperties.connectionString` and `encryptedCredential`
  are credentials: name the host, never copy the value (`write_records.py` refuses it).
- **Datasets** (`dataset/*.json`): `linkedServiceName` + `typeProperties.location`
  (container / folder / file pattern) or `schema` / `table` — the `file_dataset` and `table`
  records a `Copy` activity reads and writes.
- **Notebooks** (`notebook/*.json`, `properties.cells[].source`, language in
  `properties.metadata.language_info`, cell magics `%%sql` / `%%pyspark` / `%%spark`):
  `mssparkutils.notebook.run("name", …)` and `%run` → notebook → notebook edge;
  `spark.read.synapsesql("pool.schema.table")` / `df.write.synapsesql(…)` → pool edges;
  `.parquet("abfss://…")`, `saveAsTable`, `spark.sql("CREATE TABLE … LOCATION …")` → `file_dataset`
  and lake-database tables (shared with the serverless pool). `properties.bigDataPool` names the
  Spark pool; `properties.sessionProperties` its size.
- **SQL scripts** (`sqlscript/*.json`): the serverless pool's `OPENROWSET(BULK 'abfss://…',
  FORMAT = 'PARQUET' | 'CSV' | 'DELTA')`, `CREATE EXTERNAL TABLE` and views over ADLS — `view`
  records whose `readers` are the reports; nothing is stored, the files are the data.

**Scheduler and durations** — no SQL Agent: the triggers are the schedule, pipeline runs the
history — `az synapse pipeline-run query-by-workspace` (~45 days), or `SynapseIntegrationPipelineRuns`
/ `…ActivityRuns` in Log Analytics for the window the retention keeps; activity runs are the
per-step durations. A pool paused nightly runs its load elsewhere: note its pause / resume schedule.

**Usage on the pool** — the only basis for `orphan`:
- `sys.dm_pdw_exec_requests` keeps the **last 10,000 requests** — days, not a quarter; `command` is
  cut at 4,000 characters; `label`, `login_name`, `resource_class`, `total_elapsed_time`. Record
  the oldest `submit_time` it still holds in the manifest.
- Query Store on a dedicated pool (`ALTER DATABASE … SET QUERY_STORE = ON`) keeps **7 days**.
- A window ≥ 90 days exists only where the diagnostic settings `ExecRequests` / `SqlRequests` /
  `RequestSteps` were sent to Log Analytics (`SynapseSqlPoolExecRequests`): ask whether they are,
  and since when. Without that window nothing is `orphan`; write the question.

**Sizes** — `DBCC PDW_SHOWSPACEUSED('schema.table')` per table, or for all at once:
```sql
SELECT s.name + '.' + t.name AS [table], d.distribution_policy_desc,
       SUM(ps.row_count) AS row_count, SUM(ps.reserved_page_count) * 8 / 1024 / 1024 AS reserved_gb
FROM sys.schemas s JOIN sys.tables t ON t.schema_id = s.schema_id
JOIN sys.pdw_table_distribution_properties d ON d.object_id = t.object_id
JOIN sys.pdw_table_mappings m ON m.object_id = t.object_id
JOIN sys.pdw_nodes_tables nt ON nt.name = m.physical_name
JOIN sys.dm_pdw_nodes_db_partition_stats ps ON ps.object_id = nt.object_id AND ps.pdw_node_id = nt.pdw_node_id AND ps.distribution_id = nt.distribution_id
WHERE ps.index_id < 2
GROUP BY s.name, t.name, d.distribution_policy_desc ORDER BY reserved_gb DESC;
```
Needs `VIEW DATABASE STATE`.

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
| `schedule`, `run_as` | `sysjobschedules`, `sysjobs.owner_sid` / SSIS proxy / Control-M / Synapse `trigger/*.json` + workload classifiers |
| `avg_runtime_min` | `sysjobhistory.run_duration` averaged over ≥ 30 runs; Synapse activity runs (`SynapseIntegrationActivityRuns`) |
| `last_read_at`, `exec_count_90d` | Query Store / DBQL / `ExecutionLog3`; Synapse `SynapseSqlPoolExecRequests` (the DMV alone holds days) |
| `row_estimate`, `size_gb` | `sys.dm_db_partition_stats`, `DBA_TABLES`, `DBC.TableSizeV`, `sys.dm_pdw_nodes_db_partition_stats` |
| `pii_candidates` | Column names + sample values (masked) — never claim from names alone |
| `complexity` | Analyzer tier; do not re-score by hand |
