# Project type 2 — Greenfield lakehouse

Load when Axis A = greenfield. No central platform exists; sources are operational systems, SaaS,
files, and spreadsheets. Discovery here is interview-heavy and evidence-light, which makes the
"do not invent" rule harder to keep and more important.

## Recognising it

Signals: "nothing central", "every team has its own Excel", "we want a data platform / a
lakehouse", "single source of truth", "360 view", "we need dashboards", "we want to do AI but our
data is everywhere".

## The real driver

> "Which decision is being made badly today because the data is not there? Who makes it?"

If the answer is a concrete use case with a named decision-maker → the project has a spine. If the
answer is "we need a platform" → there is no scope yet; the assessment's first job is to find the
**first narrow use case**, and the report must say so.

## Decisions this assessment serves

- **First use case and MVP scope** — one decision, one audience, one data domain.
- **Source landscape and access feasibility** — which systems, how to get data out, at what cost.
- **Build vs buy per capability** — ingestion (Lakeflow Connect vs custom), consumption (Genie /
  metric views vs a BI build), governance model.
- **Team and skills gap**.
- **Non-functional envelope** — freshness, history, PII, cost tier.

## Sources to request

### Required

| Source | Why | How |
|---|---|---|
| **Business question list with decision owner and cadence** | Scope is defined by questions, not by source tables. Cadence drives latency | Workshop; force one named person per question |
| **The report / spreadsheet the business trusts today** | The shadow source of truth; contains business logic that exists in no system | Ask "show me the number you trust and where it comes from" |
| **Source system list** with owner, access method, and how change is exposed (CDC / `updated_at` / snapshot / files) | Determines ingestion feasibility and history depth | Interview each system owner; check vendor API docs |
| **Volumes and growth** per source | Cost tier, compute sizing | System owners; row counts via read-only queries where allowed |
| **PII / regulatory constraints** | Shapes catalog design and access model before Gold exists | Legal / DPO; existing classification if any |
| **Consumption constraints** — BI tool, Import vs DirectQuery, concurrency | Fixes the Gold grain; must be known before modelling | BI owner |

### Recommended

Existing KPI definitions (expect conflicts between departments); current manual process maps
("who touches the Excel and when"); any prior data-platform attempt and why it stalled; budget
envelope; freshness expectations per question.

### Optional

Sample extracts (masked); vendor API rate limits and pricing.

## Databricks tools to use instead of building

| Need | Use |
|---|---|
| Ingesting from SaaS / SQL Server / Postgres / files | **Lakeflow Connect** managed connectors; **Auto Loader** for files — check connector coverage before promising custom ingestion |
| Querying sources not yet ingested, during discovery | **Lakehouse Federation** (foreign catalogs, read-only) — profile without building a pipeline |
| Metric definitions | **Unity Catalog metric views** — define once; feeds SQL, dashboards, Genie |
| Business-user consumption | **Genie One / Genie Agents** on curated Gold + metric views; **AI/BI Dashboards** |
| Data quality | **Lakeflow Declarative Pipelines expectations**; **Data Quality Monitoring** |

## Conclusions the report must reach

1. **Prioritized use case list** — each with decision, owner, cadence, and the data it needs.
2. **Source specification per system** — access, change detection, volume, PII, history available
   from date. `unknown` is a valid and honest value.
3. **Target medallion sketch** at domain level (not table level — you have no data yet).
4. **Metric definition status** — which definitions are agreed, which conflict, who signs.
5. **Non-functional envelope** with cost tiers.
6. **Risks**: no data owner, no CDC at the source, shadow Excel logic, definitions unsigned.

## Evidence-sufficiency rules

| Cannot claim | Without |
|---|---|
| Any Gold table design | An agreed grain and at least one signed metric definition |
| "Source S supports incremental load" | Confirmation of CDC / reliable `updated_at`; otherwise state the snapshot-diff cost |
| "Data quality is acceptable" | Profiling on real data (Federation or a sample load) |
| "Real-time is needed" | A named action taken within minutes of the data changing |

## Confirmation questions

- "What will change in how you decide once this exists?" (kills wish-list items)
- "Two departments define *active customer* differently — measured gap is N%. Which is official, or
  are these two metrics?"
- "Which records do you deliberately exclude from today's number?" (test orders, intercompany)
- "Who is allowed to see which columns?" — before Gold, not after
- "Does this source keep history, or only current state?"

## What is routinely missed

Manual adjustments between system and report; sources with no reliable change detection; nobody
owning a definition; the BI tool's Import mode constraining Gold grain; "ingest everything just in
case"; PII discovered after the model is built.

## Cost-risk flags

Real-time by default; 10-year history at event grain; ingesting all tables of a source; serverless
always-on for a nightly use case.
