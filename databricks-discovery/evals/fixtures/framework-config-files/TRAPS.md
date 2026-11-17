# Deliberate traps in this fixture — grader reference. Do not give to the agent under test.

The framework: runner `nb_ingest_generic` (notebook), entries `config/ingest/*.json`, dispatcher
`PL_Ingest_All` (GetMetadata `childItems` → ForEach → SynapseNotebook, `pipeline/PL_Ingest_All.json:31-40`),
schedule `TR_Ingest_Daily`, daily 02:00 UTC (`trigger/TR_Ingest_Daily.json:9,29`).

Expected from `expand_flows.py expand`: **7 flows, 1 disabled, 1 read by query, 1 skipped, 0 incomplete.**

1. **The mapping comes from the code, not from the config's key names.** Every config carries a
   legacy `target_table` (`stg_…`) that the notebook never reads. The notebook's target is
   `cfg["sink"]["schema"]` + `cfg["sink"]["table"]` (`notebook/nb_ingest_generic.json:60`); the source
   is `cfg["source"].get("table")`, or `cfg["source"].get("query")` when present (`:50-53`); `enabled`
   is `cfg.get("active", True)` (`:40`); `load` is `load_type` (`:61`). A description that maps
   `target_table` writes `stg_…` targets — the miss this fixture exists for.
2. **`_defaults.json` is not a flow.** It has no `flow_name`; the script skips and lists it. An agent
   that writes it as a flow, or counts 8, has counted files instead of flows.
3. **The inactive flow is still a flow.** `wms_stock_snapshot` has `"active": false`
   (`config/ingest/wms_stock_snapshot.json:12`): recorded with `enabled: false`, a retire candidate
   whose owner confirms — never dropped from the inventory.
4. **A flow reads by query.** `tms_route_costs` has `source.query` and no table
   (`config/ingest/tms_route_costs.json:5`): `source_query` set, `reads` empty, listed by the summary.
5. **`PL_Refresh_Dim_Date` is not a framework.** One SqlPoolStoredProcedure activity, no loop; the
   same trigger runs it. It stays one ordinary pipeline record with a `calls` edge to the procedure.
6. **Counting.** Every flow number the agent states comes from the script's summary; flow records
   written by hand, or a count without `expand_flows.py`, fail the eval.
7. **Disposition.** The runner is a PySpark notebook, so `decide` defaults to `convert` (entries carried
   as configuration of a generic Databricks runner); the inactive flow `retire`; the runner and
   `PL_Ingest_All` `convert`.
