# Run layout and register schemas

One principle for every file: **machine-readable first, human-readable second**. Registers are
JSONL (one record per line) so they can be filtered, sorted, diffed, and re-read by the next skill;
the human versions (Excel, Markdown, docx) are **generated from the registers**, never the reverse.

Every record links by `id`. Prefix convention: `FR-` functional, `DR-` data, `SEC-` security,
`NFR-` non-functional, `SCOPE-` scope, `INT-` integration, `BR-` business rule, `tbl-` / `pipe-` /
`rpt-` inventory, `FND-` finding, `OQ-` open question, `src-` source.

---

## The three fields that decide quality — present in every register

| Field | Meaning | Why mandatory |
|---|---|---|
| `evidence[].kind` = `stated` \| `inferred` \| `external` | The source says it explicitly; the agent derived it; or it is general knowledge from outside the inputs (a law, vendor docs) | The line between "the document says" and "I infer". Conclusions rest on `stated` only. `external` may support a finding's *impact* or a requirement's rationale — never a fact about the client's system — and must name the reference |
| `evidence[].locator` | `file:line`, `page:section`, `transcript:hh:mm:ss`, `sheet:cell`, `object_name` | Enough for a person to open the right spot in 5 seconds. **No locator, no record** |
| `status` | `extracted` → `reviewed` → `confirmed` \| `rejected` \| `deferred` | The agent may only set `extracted`. Only a human moves it. This is the audit-trail mechanism |

Secondary but important: `confidence` (0–1, the agent's own certainty — used to order review, never
to skip it), `inferred` (bool, summary of evidence), `conflicts[]` (kept separate from evidence —
doc-vs-code disagreement is a *finding*, not evidence).

---

## `requirements.jsonl`

```json
{
  "id": "FR-01",
  "type": "functional",
  "title": "Net revenue excludes returns ≤7 days, status 9, store HCM-99",
  "statement": "Daily net revenue = sum of valid transactions minus returns within 7 days...",
  "domain": "sales",
  "priority": "must",
  "status": "extracted",
  "confidence": 0.9,
  "inferred": false,
  "evidence": [
    { "source_id": "src-sp-014", "source_type": "code",
      "locator": "sp_Calc_Daily_Revenue.sql:45-52",
      "excerpt": "WHERE t.status <> 9 AND t.store_code <> 'HCM-99'", "kind": "stated" },
    { "source_id": "src-interview-03", "source_type": "interview",
      "locator": "DBA, 2026-09-10, 00:14:30",
      "excerpt": "HCM-99 is the central warehouse, not a store", "kind": "stated" }
  ],
  "conflicts": [
    { "source_id": "src-spec-2016", "locator": "§4.1",
      "note": "Spec mentions neither the 7-day window, status 9, nor HCM-99" }
  ],
  "open_questions": ["OQ-07"],
  "related_rules": ["BR-012", "BR-013", "BR-014"],
  "target_mapping": { "layer": "silver", "object": "<catalog>.silver.transactions", "component": null },
  "owner": null,
  "extracted_by": "requirements-extraction@0.1.0",
  "extracted_at": "2026-09-14T09:12:00+07:00"
}
```

`type` is fixed: `functional | data | security | nonfunctional | scope | integration`.
`priority`: `must | should | could | wont` — set only when a source states it; otherwise `null`.
`target_mapping.object` uses the `<catalog>` placeholder until the real name is verified.

---

## `business_rules.jsonl`

Compatible with the rule register of the `legacy-spec-extraction` skill (if installed, take the
status taxonomy from there — see `legacy-etl-archaeology`).

```json
{
  "id": "BR-012",
  "name": "Exclude test transactions from revenue",
  "logic": "status <> 9",
  "plain": "Transactions with status = 9 are test transactions and do not count as revenue",
  "anchor": { "identifier": "dbo.sp_Calc_Daily_Revenue", "hash": "a3f9…" },
  "source": { "source_id": "src-sp-014", "locator": "sp_Calc_Daily_Revenue.sql:45" },
  "rule_status": "CODE-ONLY",
  "in_spec": false,
  "config_driven": false,
  "requirements": ["FR-01"],
  "open_questions": ["OQ-07"],
  "status": "extracted"
}
```

`rule_status` (distinct from review `status`): `VERIFIED | CONFLICT | CODE-ONLY | DOC-ONLY |
CONFIG-ONLY | DEAD | UNRESOLVED`. The distribution of this field over time is the **real progress
metric** of discovery — report it instead of page counts.

---

## `inventory_tables.jsonl`, `inventory_pipelines.jsonl`, `inventory_reports.jsonl`

```json
{ "id": "tbl-0087", "name": "MP_DWH.dbo.STG_POS_TXN", "kind": "table",
  "layer_guess": "bronze", "row_estimate": 730000000, "size_gb": 412,
  "writers": ["pipe-0031"], "readers": ["pipe-0044", "rpt-0012"],
  "last_read_at": "2026-09-09", "last_write_at": "2026-09-13",
  "pii_candidates": [], "orphan": false,
  "complexity": null, "complexity_source": null, "disposition": null,
  "evidence": [{ "source_id": "src-analyzer-01", "locator": "analyzer_out.xlsx:Objects!row 88", "kind": "stated" }],
  "status": "extracted" }

{ "id": "pipe-0031", "name": "SSIS:pkg_pos_load", "kind": "ssis_package",
  "schedule": "daily 01:00", "avg_runtime_min": 42, "reads": ["tbl-0012"], "writes": ["tbl-0087"],
  "complexity": "medium", "run_as": "svc_etl", "disposition": null,
  "evidence": [...], "status": "extracted" }

{ "id": "rpt-0012", "name": "SSRS:Daily Revenue by Store", "kind": "ssrs_report",
  "consumers": ["Finance"], "exec_count_90d": 184, "last_exec_at": "2026-09-12",
  "reads": ["tbl-0102"], "disposition": null,
  "evidence": [...], "status": "extracted" }
```

`complexity_source`: `analyzer | manual | null`. A manual tier is triage, not measurement — the
report must say so wherever the tier appears.
`disposition` is the rationalization-matrix field: `migrate | modernize | retire | defer | null`.
**Only `assessment-synthesis` sets it**, and only with usage evidence.
`orphan = true` only when a usage log of sufficient length exists (see the project-type module on
the month-end / year-end trap).

---

## `dependency_edges.jsonl`

```json
{ "from": "pipe-0031", "to": "tbl-0087", "kind": "writes", "evidence": [...] }
{ "from": "tbl-0087", "to": "pipe-0044", "kind": "reads", "evidence": [...] }
{ "from": "pipe-0044", "to": "pipe-0045", "kind": "triggers", "evidence": [...] }
```

`kind`: `reads | writes | triggers | calls | depends_on`. Generate Mermaid/DOT from this file; never
draw by hand.

---

## `findings.jsonl`

```json
{ "id": "FND-03", "severity": "high", "category": "data_quality",
  "title": "3% of POS transactions with no matching store are silently dropped by an INNER JOIN",
  "detail": "sp_Calc_Daily_Revenue line 61 INNER JOINs dim_store; profiling shows 3.1% of txns have a store_code that does not exist",
  "evidence": [{ "source_id": "src-sp-014", "locator": "sp_Calc_Daily_Revenue.sql:61", "kind": "stated" },
               { "source_id": "src-profiling-02", "locator": "profiling run 2026-09-12, query Q7", "kind": "stated" }],
  "impact": "Reported revenue is ~3% below actual; nobody knows because nothing is logged",
  "requirements_raised": ["DR-01"], "questions_raised": ["OQ-11"],
  "status": "extracted" }
```

`severity`: `critical | high | medium | low`. `category`: `data_quality | logic | security |
cost | performance | governance | scope | dependency | documentation`.

---

## `open_questions.jsonl`

```json
{ "id": "OQ-07",
  "question": "Should HCM-99 still be excluded from revenue? Since when, and why?",
  "why": "The rule exists in code but not in the 2016 spec; if kept wrongly, revenue is off by the largest store",
  "evidence": [{ "source_id": "src-sp-014", "locator": "sp_Calc_Daily_Revenue.sql:52", "kind": "stated" }],
  "ask": "Head of Accounting (name: ?)",
  "default": "Keep the rule as in current code; mark CONFLICT",
  "impact_if_wrong": "high",
  "blocking": ["FR-01", "BR-014"],
  "status": "open",
  "asked_at": null, "answered_at": null, "answer": null }
```

`ask` is a **person**, not a department. If the name is unknown, write the role plus `(name: ?)`
and make finding the name part of the question. Each turn sends the user ≤ 5 questions with
`impact_if_wrong = high`.

---

## `manifest.json` — inside every `runs/<date>_run-NN/`

```json
{
  "run_id": "2026-09-14_run-07",
  "skill": "requirements-extraction@0.1.0",
  "model": "<model id>",
  "project": "minhphat-migration",
  "sources_read": [
    { "source_id": "src-sp-014", "path": "<original path on disk>/sp_Calc_Daily_Revenue.sql", "sha256": "…", "bytes": 18402 }
  ],
  "sources_requested_not_available": ["src-querystore"],
  "external_access": [],
  "counts": { "requirements": 12, "business_rules": 31, "findings": 4, "open_questions": 9 },
  "notes": "Docs were not loaded while reading code (code-first rule); diffed against the spec in step 3"
}
```

`external_access` lists **every** access beyond local files: endpoint, statement executed, rows
returned. Empty means the run was pure file reading. This is what the client will ask about.

---

## `intake.md` — template

```markdown
# Intake — <project>  (updated: 2026-09-14, run-07)

## Axis A — Project type
- Primary: **migration / modernization**  `inferred` — from "SQL Server license ends 2026-12" (src-kickoff-01, 00:03:10)
- Secondary: cost & performance  `inferred` — nightly chain 5.5h overruns the window (src-kickoff-01, 00:11:40)
- Real driver: [stated | inferred] …
- To confirm: OQ-01

## Axis B — Inputs per source system
| Source system | Level | In hand | Missing to reach next level |
|---|---|---|---|
| MP_DWH (SQL Server) | L2 | 87 sps, 340 DDL (src-code-01) | Query Store / usage log → L3 |
| SAP (PO) | L0 | verbal only | any export at all |

## Axis C — Decision
> This report is for **[CTO Minh Phát — name: ?]** to decide **scope and budget for migration wave 1**
> before **2026-10-15**.  `assumed` — confirm via OQ-02

## Blocking questions this turn (≤5)
1. OQ-01 …
```

---

## `source_request.md` — template

```markdown
# Source request — <project>  (module: migration)

## Required — without these the core conclusions cannot be reached
| # | Source | Why needed | How to obtain | Client owner | Status |
|---|---|---|---|---|---|
| 1 | Read-only service principal on SQL Server + read on msdb, ReportServer | everything below | DBA creates the login; needed by … | DBA (name: ?) | ⏳ requested 09-14 |
| 2 | Script of all objects (DDL + sps + views + functions) | inventory + rules | SSMS Generate Scripts or `mssql-scripter`; export as folders | DBA | ✅ src-code-01 |
…
## Recommended
## Optional
```

---

## `sufficiency.md` — template

```markdown
# Evidence sufficiency — <project>  (run-07)

| Conclusion needed | Evidence required | In hand | State | If missing |
|---|---|---|---|---|
| Scope: which tables migrate/retire | inventory + usage ≥90 days incl. month-end | inventory ✅ src-analyzer-01; usage ❌ | ❌ | no table may be called orphan |
| Effort wave 1 | complexity/object + trial auto-convert rate | complexity ✅; trial ❌ | ⚠️ | range only; state Converter not yet trialled |
| Usage window (always present) | log source, start, end; restart time if DMV-based | Query Store 2025-08-12→2026-09-12 ✅; `sqlserver_start_time` 2026-09-01 noted | ✅ | DMV-only usage would cover ≤ 11 days and prove nothing |
```

---

## `review.md` — template, one page

```markdown
# Review — run-07  (requirements-extraction@0.1.0, 2026-09-14)

**Read:** 87 stored procs (src-code-01), 2016 spec (src-spec-2016) — docs loaded AFTER code.
**Produced:** 12 requirements · 31 business rules · 4 findings · 9 open questions.

## Needs a human decision now (impact high)
- OQ-07 HCM-99 — ask Head of Accounting
- OQ-11 3% unmatched transactions — ask POS business owner

## rule_status distribution
VERIFIED 6 · CONFLICT 3 · CODE-ONLY 19 · CONFIG-ONLY 2 · DEAD 1 · UNRESOLVED 0

## Where I am unsure (confidence < 0.6)
- BR-020 — discount allocation has two branches; unclear which runs in prod

## Deliberately NOT concluded for lack of evidence
- Orphan tables — no usage log yet

## How to merge
Edit directly in `runs/…/*.jsonl`, move `status` → `reviewed`/`confirmed`/`rejected`, then merge into `registers/`.
```
