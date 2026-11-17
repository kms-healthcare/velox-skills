# Fixture: framework-config-files

A synthetic Azure Synapse workspace (Git export) whose ingestion is a metadata-driven framework:
one generic PySpark notebook runs one flow per JSON config file, called from a pipeline that lists
the config folder and loops over it. For testing that `legacy-etl-archaeology` reads the
framework as one pipeline per configured flow through `expand_flows.py`, with the mapping taken
from the notebook's code (VEL-1723). The config folder was copied from the lake's `config`
container (`config/ingest/`). Everything under `sources/` is what the agent receives. `TRAPS.md` is
for graders only. Run live by a model (eval 6 in `../../evals.json`); the script half is checked by
`legacy-etl-archaeology/scripts/test_expand_flows.py::test_fixture_config_files`.

Test prompt:

> Lumen Freight's ingestion runs in an Azure Synapse workspace; the Git export of its pipelines,
> notebooks, triggers and the ingestion config folder is in sources/. Run the archaeology on it
> before we plan the move to Databricks: inventory, dependencies and a rationalization draft.
