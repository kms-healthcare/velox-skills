---
name: cost-performance
description: "Review what a Databricks workspace spends and where, from the system-table reads Velox saved in the project (billing, jobs and query history, as aggregates, at list price) — and write cost and performance findings, each with its saving, its trade-off and the saved file it rests on, plus an open question for every view that could not be read. Use when the turn says to load cost-performance, for a cost review, a FinOps review, 'why is the bill rising', 'which jobs cost the most', or the cost section of an assessment. Reads files only: never queries a workspace, never changes a setting."
compatibility: "Reads JSON files. The reads are made before the turn by Velox (the Velox Databricks App's read_system_tables, one file per view)."
metadata:
  version: "0.1.0"
  parent: discovery-intake
---

# Cost & performance — from the reads Velox saved, nothing else

A cost review on Velox reads each workspace through its own Velox app **before** you are asked:
`read_system_tables`, five views, the last 30 days, saved in the project as

```
assessment/<project>/system-tables/<date>/<env>/<view>.json
  cost_by_day · cost_by_job · cost_by_warehouse · jobs · queries_by_warehouse
assessment/<project>/system-tables/<date>/not_measured.json
  {"not_measured": [{"workspace": "PROD", "reason": "Velox not installed"}]}
```

The turn names the folder, every view or workspace that was not read and why, and the run folder to
write. **You do not query the workspace.** No SQL, no `databricks` command, no other app tool: the
files are the evidence, and the same five views every time is what makes two reviews comparable.

## What is in the files

| View | Rows | Use it for |
|---|---|---|
| `cost_by_day` | per day, product (`JOBS`, `SQL`, `ALL_PURPOSE`, `DLT`, …) and unit | the total, the trend, what kind of compute spends it |
| `cost_by_job` | per job id, most expensive first | the job cost drivers and their share of the total |
| `cost_by_warehouse` | per SQL warehouse id, most expensive first | the warehouse cost drivers |
| `jobs` | the top jobs with `name`, `runs`, `run_seconds`, `dbu`, `list_cost`, and `code` (notebook paths, Python files, Git source) or a `note` | what each expensive job is, how often it runs, what it runs |
| `queries_by_warehouse` | per warehouse and statement type: `statements`, `total_seconds`, `avg_seconds`, `read_bytes`, `produced_rows` — never a statement's text | the load on each warehouse, slow statement types |

Every answered file carries `since`, `until`, `price: "list"`, `currency` and `notes` (the billing
lag, SKUs with no list price). A view the app refused is `{"view": …, "refused": "<the app's words>"}`.

## Rules

Each rule names the view it reads. Write a finding only when the numbers in the files support it.

1. **Top cost drivers.** The jobs and warehouses that make most of the total (`cost_by_job`,
   `cost_by_warehouse` against the sum of `cost_by_day`), each with its share. A driver is a fact,
   not a finding, unless something below explains why it costs what it does.
2. **All-purpose compute for scheduled work.** `ALL_PURPOSE` holding a large share in `cost_by_day`
   while `jobs` shows scheduled runs: jobs on interactive clusters pay the all-purpose rate. `cost`.
3. **A warehouse that costs more than it works.** High `list_cost` in `cost_by_warehouse` against
   few `statements` or little `total_seconds` in `queries_by_warehouse`: idle time, a long auto-stop
   or a size the load does not need. `cost`. Trade-off: cold starts for the first query after a stop.
4. **A job that runs more than its data needs.** Many `runs` and steady `dbu` per run for a job whose
   name or code points at a full reload (`jobs`). `cost`. Trade-off: an incremental load needs a
   watermark and a backfill path.
5. **Slow statement types.** A statement type whose `avg_seconds` or `read_bytes` per statement
   stands out on its warehouse (`queries_by_warehouse`). `performance`. You cannot see which query,
   so say which warehouse and type, and ask who owns it.
6. **A rising spend.** A product whose daily cost rises across the window (`cost_by_day`). 30 days
   show a trend, not a month end: say so.
7. **What you cannot price.** A SKU in `notes` with no list price: its cost is left out of every
   total; name it.

## Every finding

`findings.jsonl` in the run folder, through `write_records.py` (discovery-intake), with the fields
every reviewed record carries (`meaning`, `impact`, `risk`, `recommendation`) and:

- `category`: `cost` or `performance`; `severity` by the share of the total it touches;
- `evidence[0]`: the saved file and line, relative to the project root —
  `assessment/<project>/system-tables/<date>/dev/jobs.json:14`, `kind: stated`. **No saved file, no
  finding.** A second file when two views agree;
- `saving`: `{"amount": 43, "currency": "USD", "per": "day", "basis": "list price"}` — only a number
  the views support, worked from them (say how in `detail`); `null` when they do not. Never a saving
  from a price sheet ("serverless saves X" needs a trial, not a list price);
- `trade_off`: what the change costs — an SLA it touches, a cold start, a backfill. Ask the owner
  when the files cannot say (an open question);
- `migration_disposition`: left to `assessment-synthesis`. A finding that changes no decision is
  marked `none` there and stays out of the report unless it is critical or high.

Amounts are at **list price, not the client's rates** — write it that way in `impact`.

## A job's code

`jobs.code` is there only where the job is shared with the app's service principal (CAN VIEW). Where
`note` says Velox may not read the job's definition, **never say what the job does**: say what it
costs and how often it runs, and raise an open question to the job's owner to share it. A `note` for
a one-time run or a deleted job is a fact, not a gap.

## What was not read

- **A view refused** (the turn: "<ENV>'s <view> could not be read: <the app's words>"): one open
  question per view, `ask` the role the words name (an account admin enables a schema, a metastore
  admin grants the app's service principal), `default`: "Leave <view> out of the review", `impact_if_wrong`
  by what the view would have shown. Copy the app's words into `why`; do not reword them.
- **A workspace not measured** (no Velox, or its app did not answer): no finding about it. Velox
  saves the list with each reason in `system-tables/<date>/not_measured.json`, and the report names
  them from it (`assessment-synthesis` §8a). Do not write a list of your own.

## Then

Write `review.md` for the run, as every run does, and build the DRAFT report (`assessment-synthesis`,
`--include-unreviewed`). Its §8a carries what was measured, where, over which dates, at list price,
the most expensive jobs and warehouses, the workspaces not measured, and your findings — every
number in it is computed from the saved files by the generator, not written by you.

## Boundaries

Files only. No query, no write, no setting changed, no job paused. The client's negotiated prices,
costs outside DBU (storage, egress, VMs) and cloud billing are out of scope: say so when the person
asks for a total platform cost. Optimizations as a migration plan are another workflow.

## References

`../discovery-intake/references/project-type-cost-performance.md` (the project type, what to
request beyond these views) · `../discovery-intake/references/run-layout.md` (finding and question
schemas) · `../assessment-synthesis/SKILL.md` (§8a).
