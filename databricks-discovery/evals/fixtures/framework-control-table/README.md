# Fixture: framework-control-table

A synthetic Azure Synapse workspace (Git export) whose ingestion is the "metadata-driven copy"
form of a framework: one control table, read by two dispatcher pipelines (hourly and daily), each
looping over its rows and calling one parameterised Copy pipeline per row. For testing that
`legacy-etl-archaeology` reads it as one pipeline per row through `expand_flows.py`, routed between
the two dispatchers, with the on/off switch kept apart from the routing and no connection string
reaching a register (VEL-1723). The table's rows were exported from the dedicated pool
(`exports/ctl_IngestControl.csv`); its DDL is in `ddl/`. Everything under `sources/` is what the agent
receives. `TRAPS.md` is for graders only. Run live by a model (eval 7 in `../../evals.json`); the
script half is checked by `legacy-etl-archaeology/scripts/test_expand_flows.py::test_fixture_control_table`.

Test prompt:

> Lumen Freight also lands ERP and CRM tables with Synapse pipelines driven by a control table;
> sources/ holds the pipeline and trigger JSON, the table's DDL and an export of its rows. Run the
> archaeology and draft the rationalization.
