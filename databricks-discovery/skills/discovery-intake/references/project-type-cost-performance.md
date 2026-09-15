# Project type 4 — Cost & performance

Load when Axis A = cost & performance. The platform already runs on Databricks; the bill or the
run windows are the problem. This is the most quantifiable type — and the one where an agent
without system-table access has **nothing** to say. Say so if that is the situation.

## Recognising it

Signals: "the bill doubled", "jobs overrun the window", "dashboards time out", "finance is asking",
"we need to cut 30%", "which cluster costs what". Often arrives disguised as migration ("move to
serverless") or consolidation.

## The real driver

> "Is the target a number (budget), a time (SLA), or an explanation (who spends what)?"

| Driver | What it changes |
|---|---|
| Budget cut of X% | Rank cost drivers; quick wins first; know which jobs have hard SLAs before touching them |
| SLA broken | Critical-path analysis of the job DAG; cost is secondary |
| "Explain the bill" | Attribution: tags, owners, workspaces — a governance deliverable more than an engineering one |

## Decisions this assessment serves

Where to cut first; which jobs to re-architect vs re-size; compute policy and warehouse settings;
tagging / cost-allocation model; whether serverless pays off **for these workloads**.

## Sources to request

### Required

| Source | Why | How |
|---|---|---|
| `system.billing.usage` joined to `system.billing.list_prices`, **≥ 90 days** | Cost by SKU, workspace, cluster/warehouse/job/endpoint; trend | Read on `system.billing`; account admin enables the schema |
| `system.compute.clusters` + `system.compute.node_timeline` | Configuration and minute-level utilisation → idle and oversized compute | `system.compute` |
| `system.lakeflow.jobs` + `job_run_timeline` + `job_task_run_timeline` | Run durations, failures, retries, which jobs never run | `system.lakeflow` |
| `system.query.history` | Slow and expensive queries, warehouse load, who runs what | `system.query` |
| **Cluster policies, warehouse configs, auto-termination settings** | Explains most idle spend | Workspace admin export or API |
| **Tags / cost-center mapping** | Without it nothing can be attributed | Admin; if absent, that is finding #1 |
| **SLA list for the top-N jobs and dashboards** | Defines what may be slowed or moved | Job owners; if nobody knows, that is a finding |

### Recommended

**Cloud bill** for the same period (storage, egress, VMs, networking are **not** in DBUs — a common
30–50% blind spot); table maintenance state (`OPTIMIZE`/`VACUUM` history, small files, liquid
clustering, predictive optimization on/off); Photon enabled or not; streaming jobs list and whether
they truly need 24/7.

## Databricks tools to use instead of building

| Need | Use |
|---|---|
| Cost overview, top-N, forecast | **Usage Dashboard** (system tables) with `AI_FORECAST`; **budget policies** for alerts |
| Guardrails | **Compute policies**; warehouse auto-stop; serverless where the workload is spiky |
| Table performance | **Predictive optimization**, liquid clustering, Photon |
| Query fixes | **Genie Code** for rewriting individual slow queries — after the assessment identifies which |

## Conclusions the report must reach

1. **Top cost drivers** (cluster / warehouse / job / endpoint) with owner, trend, and share of total.
2. **Utilisation findings**: idle all-purpose clusters, oversized nodes, warehouses without auto-stop,
   24/7 streaming for nightly-consumed data.
3. **Job runtime trend** and the critical path of the longest chain.
4. **Query anti-patterns** by cost (full scans, no partition pruning, `SELECT *` into BI).
5. **Quick wins vs re-architecture**, each with the SLA it touches.
6. **Attribution gaps** — untagged spend as a percentage.
7. **Cloud costs outside DBUs**, stated separately.

## Evidence-sufficiency rules

| Cannot claim | Without |
|---|---|
| A trend | ≥ 30 days; ≥ 90 to see month-end |
| "Team T spends X" | Tags or a workspace→team mapping; otherwise report "unattributed: N%" |
| "Job J can be slowed / moved to spot" | Its SLA, from an owner |
| "Serverless saves X" | A measured trial on representative jobs, not the price sheet |
| "Total platform cost is X" | The cloud bill as well as DBUs |

## Confirmation questions

- "Cluster C ran 720 h last month at 8% CPU (locator). Who owns it, and what runs on it?"
- "Job J has consumed 18% of DBUs and has no listed owner. Can it be paused for a week to see who
  notices?" (a legitimate discovery technique — with consent)
- "Which dashboards must load in under N seconds, and for how many concurrent users?"
- "Are these streaming jobs feeding anything that is read more than once a day?"

## What is routinely missed

Cloud costs outside DBUs; all-purpose clusters used for scheduled jobs; forgotten 24/7 streams;
warehouses with long auto-stop; Photon off; small files / no `OPTIMIZE`; BI Import refreshes
spinning warehouses; dev workspaces at production size.

## Cost-risk flags

Cutting cluster size before knowing SLAs; moving to serverless by price sheet; "turn everything
off at night" when month-end jobs run at night.
