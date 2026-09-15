# Project type 3 — Platform / consolidation

Load when Axis A = consolidation. Multiple workspaces, metastores, or platforms exist — after
mergers, organic growth, or shadow IT — and the client wants one governed platform. Discovery here
is dominated by **system tables and scanners**; interviews confirm ownership, they do not provide
the inventory.

## Recognising it

Signals: "many workspaces", "each team has its own", "merger / acquisition", "we don't know who
uses what", "permissions are a mess", "hive_metastore", "audit finding", "duplicate spend".

## The real driver

> "What forced this now — an audit, a bill, a merger, or an incident?"

| Driver | What it changes |
|---|---|
| Audit / compliance finding | SAT output and access model are the centre; deadline is external |
| Duplicated spend | Load `project-type-cost-performance.md`; usage evidence decides what to shut down |
| Merger | Two of everything; identity and network first, data second |
| Incident (leak, deletion) | Security posture and governance model; tolerance for change is high — use it |

## Decisions this assessment serves

- **Target topology**: one metastore per region, catalog-per-domain vs catalog-per-environment,
  workspace boundaries.
- **Decommission list** with owners and dates.
- **Governance model**: who owns catalogs, how access is granted, tagging and cost allocation.
- **Migration order** (hive_metastore → Unity Catalog; workspace merges) and what breaks.

## Sources to request

### Required

| Source | Why | How |
|---|---|---|
| **Account-level admin read access** (or exports) across all workspaces | Nothing can be concluded per-workspace from one workspace | Account admin; request on day one |
| **System tables**, account-wide, ≥ 90 days: `system.billing.usage` + `list_prices`, `system.access.audit`, `system.access.table_lineage`, `system.lakeflow.jobs` + `job_run_timeline`, `system.compute.clusters`, `system.query.history` | Who uses what, what costs what, what is idle — the actual inventory | System schemas must be enabled by an account admin; query from any UC-enabled workspace |
| **Workspace list with owners, purpose, environment (dev/test/prod), and creation date** | Scope and decommission candidates | Account console; then confirm owners by interview |
| **UC adoption state per workspace**: UC-enabled? hive_metastore tables still in use? mounts? | The hive_metastore → UC migration is usually the largest work item | **UCX assessment** (Databricks Labs) per workspace — it inventories tables, jobs, clusters, grants, mounts and produces an assessment dashboard |
| **SAT output** per workspace | Security posture against Databricks best practices, ranked by severity | Run **Security Analysis Tool**; do not rebuild the checklist |
| **Identity setup**: SCIM source, groups, service principals and their owners | Access model cannot be designed without it | Account admin; IdP admin |

### Recommended

Network topology (VNet/VPC, private link, egress); external locations and storage credentials
(look for two workspaces pointing at the same storage); existing tags / cost-center mapping; data
sharing between workspaces (Delta Sharing, copies); compliance boundaries (regions, regulated data).

## Databricks tools to use instead of building

| Need | Use |
|---|---|
| hive_metastore → Unity Catalog readiness | **UCX** — assessment workflow + migration commands |
| Security posture | **SAT** — multi-cloud, severity-ranked, schedulable |
| Cost per workspace / team / SKU, forecast | **Usage Dashboard** on system tables, `AI_FORECAST`, budget policies |
| Architecture rubric | **Well-Architected Framework** — five pillars: Secure, Reliable, Efficient, Interoperable, Cost-effective; nine-phase deployment guide |
| Lineage across workspaces | `system.access.table_lineage` / `column_lineage` (rolling 1 year) |

## Conclusions the report must reach

1. **Workspace inventory** with owner, purpose, environment, cost, active users, last activity.
2. **Duplication findings** — same data in two places, same job twice, two workspaces on one bucket.
3. **Governance gaps** against WAF pillars and SAT severity — as `SEC-` / `NFR-` requirements, not
   as a checklist dump.
4. **UC migration scope** from UCX: tables, jobs, clusters, mounts, grants that must move.
5. **Target catalog and workspace design** with the trade-offs stated.
6. **Decommission list** — each with evidence of no usage and a named owner who agrees.
7. **Migration order** by dependency and risk.

## Evidence-sufficiency rules

| Cannot claim | Without |
|---|---|
| "Workspace W is unused" | `system.access.audit` + `query.history` + `job_run_timeline` for ≥ 90 days incl. month-end |
| "Cost can drop by X" | Per-workspace usage joined to `list_prices`, and knowledge of which jobs have SLAs |
| "UC migration is N tables" | UCX assessment output, not a manual count |
| "Security is acceptable" | SAT run on **every** workspace, not the main one |

## Confirmation questions

- "Workspace W: 0 queries, 2 job runs in 90 days (locator). Decommission, or is it DR / year-end?"
- "These two external locations point at the same storage path (locator). Intentional?"
- "Who owns service principal SP-x? It runs 14 jobs and nobody claims it."
- "Which data must stay in region R / cannot leave workspace W?"
- "Dev workspaces hold production data copies (locator). Allowed?"

## What is routinely missed

Personal / sandbox workspaces; orphaned service principals; hive_metastore tables still read by
one critical job; cross-workspace jobs via Delta Sharing or direct storage paths; identity groups
managed in two IdPs after a merger; cloud costs outside DBUs (storage, egress, VMs).

## Cost-risk flags

Big-bang consolidation; moving everything to serverless without measuring; migrating unused
workspaces "for completeness".
