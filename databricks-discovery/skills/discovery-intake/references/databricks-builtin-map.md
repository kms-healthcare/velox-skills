# What Databricks already ships — check before building anything

Use this before proposing to "build an agent / tool that does X". The pattern: Databricks
built-ins are strong **inside a workspace, once data is there, for end users**. They are largely
absent **before the lakehouse exists, when the deliverable is a client document, when the output
must be traceable and human-reviewed**. That gap is discovery & assessment.

## Renamed in 2026 — use both names when talking to clients

| Old name | Current name | What it is |
|---|---|---|
| Databricks Assistant | **Genie Code** | Coding agent in the workspace; Agent mode GA (03/2026) |
| Genie space | **Genie Agent** | Domain NL→SQL environment |
| — | **Genie One** | Business-user front door |
| Vector Search | **AI Search** | Retrieval indexes |
| Delta Live Tables (DLT) | **Lakeflow Declarative Pipelines** | Declarative ETL with expectations |
| `APPLY CHANGES INTO` | **AUTO CDC** | CDC / SCD in pipelines |
| Lakehouse Monitoring | **Data Quality Monitoring** | Profile and drift metrics tables |

## Runs inside the workspace, serves runtime

| Tool | Does | Status | Discovery relevance |
|---|---|---|---|
| Genie Agents / Genie One | NL→SQL on curated tables; instructions + example SQL + trusted assets; ≤100 instructions + 200 knowledge snippets; **no unstructured docs** | GA | Consumption design target; not a discovery tool |
| Genie Code | Builds notebooks, EDA, fixes errors, finds tables in UC | GA | Useful once data is in UC; useless before |
| Agent Bricks: Knowledge Assistant, Document Intelligence / Information Extraction, Custom LLM, Supervisor | Configurable agents over your data; auto-optimised | mostly GA | Build-vs-buy answer for ML/AI type; **not** a delivery-assessment tool |
| Unity Catalog metric views + Business Semantics (Pages, certification) | Governed metric definitions in YAML; feeds SQL, dashboards, Genie | GA 04/2026 | **Target home for metric definitions** discovered in requirements |
| Usage Dashboard + system tables + `AI_FORECAST` + budget policies | Cost observability and forecast | GA | Primary evidence for cost & consolidation types |
| Data Quality Monitoring | Profile + drift metrics tables | GA | Free profiling where already enabled |
| Lakehouse Federation | Query external DBs via UC foreign catalogs, read-only | GA | **Profile sources before ingesting** — key for greenfield discovery |
| Lakeflow Connect | Managed ingestion connectors (SQL Server CDC, SaaS) | GA (per connector) | Shapes source-spec questions (is CDC enabled?) |

## Bridges for agents running outside

| Tool | Does | Status |
|---|---|---|
| **Managed MCP servers** | Databricks-hosted MCP for Genie Agents, UC functions, AI Search; custom MCP on Databricks Apps; UC enforces permissions | GA early 2026 |
| Databricks CLI / Python SDK | Everything else; auth via service principal OAuth M2M | GA |
| **Official agent skills** `databricks/databricks-agent-skills` | 29 skills, all implementation (jobs, pipelines, DABs, UC, metric views, Genie, Apps, MLflow…). `databricks aitools install`. **None for discovery / assessment / requirements** | active |

## Free tools that overlap with assessment work — use, do not rebuild

| Tool | Does | Use it for |
|---|---|---|
| **Lakebridge** (Databricks Labs) — Analyzer / Transpiler / Reconcile | Inventory + complexity of legacy code (40+ source techs, `.xlsx` + `.json`); conversion; data reconciliation | Migration inventory and estimate drivers. Does **not** extract business rules in business language or flag rules missing from specs |
| **UCX** (Databricks Labs) | hive_metastore → Unity Catalog assessment and migration | Consolidation and any client still on hive_metastore |
| **SAT — Security Analysis Tool** | Scans account + workspace config against best practices; severity-ranked report; multi-cloud; schedulable | Security posture in consolidation / migration. Translate its output into `SEC-` requirements; do not write your own checklist |
| **Well-Architected Framework** | Five pillars — Secure, Reliable, Efficient, Interoperable, Cost-effective — and a nine-phase deployment guide | Rubric for platform findings |

## What none of them do — the space this skill pack occupies

- Determine the project type from the real driver and pin the decision the assessment serves.
- Extract requirements from documents and interviews **with locators, confidence, conflicts, and open
  questions**, reviewable by a human before they become truth.
- Extract business rules from legacy code in business language and mark which ones are absent from
  the spec (`CODE-ONLY`, `CONFLICT`).
- Decide `migrate | modernize | retire | defer` per object with evidence.
- Write the assessment report as a decision instrument with an evidence-sufficiency appendix.
