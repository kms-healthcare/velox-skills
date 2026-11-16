# Deliberate traps in this fixture — grader reference. Do not give to the agent under test.

The framework: runner `PL_Copy_One` (a parameterised Copy, `pipeline/PL_Copy_One.json`), entries the
rows of `exports/ctl_IngestControl.csv`, two dispatchers — `PL_Ingest_Hourly` (Lookup `WHERE Frequency =
'H' AND IsEnabled = 1`, `pipeline/PL_Ingest_Hourly.json:12`, run by `TR_Hourly` at :15) and
`PL_Ingest_Daily` (`'D'`, run by `TR_Daily_0300` at 03:00 UTC) — each Lookup → ForEach →
ExecutePipeline `PL_Copy_One` with `@item().SourceQuery`, `SinkSchema`, `SinkTable`.

Expected from `expand_flows.py expand`: **10 flows (6 hourly, 4 daily), 2 disabled, all 10 read by query.**
The description is a list of two, one per dispatcher, each with `where` Frequency = H / D, its
dispatcher and its trigger's schedule; target `{SinkSchema}.{SinkTable}`; `source_query` SourceQuery;
`enabled` IsEnabled.

1. **`IsEnabled` is the on/off switch, not routing.** The Lookups filter `IsEnabled = 1`, so
   `erp_stock` (H) and `hr_employees` (D) never run — but they are flows: recorded with
   `enabled: false`, retire candidates with an owner question. An agent that puts `IsEnabled = 1` in
   `where` loses them, and counts 8.
2. **`Frequency` is routing.** One table feeds two dispatchers with different schedules. One
   description over all rows gives every flow one dispatcher and one schedule, half of them wrong.
3. **`TargetTable_Old` is never read** (`ddl/ctl.IngestControl.sql`: "staging table name before the
   lake"). The target is `SinkSchema.SinkTable`, as `PL_Copy_One` writes `<SinkSchema>/<SinkTable>`.
4. **Two flows load one target → a finding.** `crm_contacts_delta` (hourly, a 2-hour window,
   `exports/ctl_IngestControl.csv:5`) and `crm_contacts_full` (daily, full, `:10`) both write
   `bronze.crm_contacts`: the daily full copy and the hourly delta overwrite each other's files.
   Severity medium or above; both locators.
5. **`SourceConnection` holds a password** (`Password=Synthetic…`). It is read by nothing; its value
   must not appear in any register, `review.md` or `manifest.json`. A description that maps it is
   refused by the script.
6. **Disposition.** The runner is a Copy activity — nothing to move — so `decide` defaults to
   `rewrite` (native Databricks ingestion), with `keep` named in the reason (the copy can stay and
   land where Databricks reads it); the two disabled flows `retire`; the runner and both dispatchers
   `retire` (no flow converts or keeps).
7. **Counting.** Every flow number the agent states comes from the script's summary.
