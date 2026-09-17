---
name: legacy-etl-archaeology
description: "Recover business rules, dependencies, and inventory from legacy DW/ETL code before migrating it to Databricks - T-SQL, PL/SQL and Teradata procedures, views, SSIS, Informatica, DataStage, scheduler jobs, report logic. Produces a business-rule register with VERIFIED / CONFLICT / CODE-ONLY / CONFIG-ONLY / DEAD statuses, a dependency graph, and inventory with real usage, all with code locators. Use when the user has legacy code and asks what these stored procedures do, which rules are missing from the spec, which tables are orphan, or how to prepare for Lakebridge. Does not convert code and does not replace Lakebridge Analyzer."
metadata:
  version: "0.2.0"
  parent: discovery-intake
  compatibility: "Runs outside Databricks. Filesystem; Python 3.9+ optional. Uses legacy-spec-extraction's method and scripts when installed."
---

# Legacy ETL archaeology — what the code does, and what nobody wrote down

| Reads legacy code | Answers | Does not |
|---|---|---|
| **Lakebridge Analyzer** — `databricks labs lakebridge analyze --source-directory … --report-file … --source-tech … --generate-json true` | how many objects, what kind, how complex, what depends on what | what a rule *means*, whether it is documented, whether it is wanted |
| **`legacy-spec-extraction`** (Velox) | the method: rule register, status taxonomy, identifier anchors, calibration | DW specifics: SSIS, scheduler DAGs, report logic, usage logs |
| **this skill** | applies the method to DW/ETL artifacts on top of Analyzer output; emits the registers the assessment needs | conversion (Transpiler), platform design (`assessment-synthesis`) |

If `legacy-spec-extraction` is installed, read its `SKILL.md` and `references/rule-register.md`
first and use `scripts/anchor_hash.py`. Schemas and record budget:
`../discovery-intake/references/run-layout.md`. Rules 1–3 of `discovery-intake` apply.

## The rule that matters most: code first, documents second

**Never read documentation and code in the same pass.** With both in context the model uses the
docs to interpret the code and produces a seamless spec — seamless exactly where the system drifted
from its documentation. Derive rules from code alone; then load `requirements.jsonl` or the docs and
diff; record every disagreement as `CONFLICT` and never resolve it yourself. Exception: a glossary
or data dictionary may be loaded first — names, not behaviour.

`CONFLICT` and `CODE-ONLY` are the highest-value output of the whole assessment. `sp_Calc_Daily_Revenue`
excludes `store_cd = 'HCM-99'`; the spec never mentions it; Lakebridge will transpile the predicate
faithfully and nobody will ask why. This skill exists so that someone asks.

## Inputs

Exported object scripts (one file per object — run the Analyzer on that folder, register the JSON
as `src-analyzer-01`) · SSIS `.dtsx` / Informatica XML / DataStage `.dsx` / ADF JSON · scheduler
exports (`msdb.dbo.sysjobs/steps/schedules/history`, Control-M) — the real DAG and **actual
durations** · report definitions (`.rdl`, Cognos) — rules that live in no procedure · usage logs
(Query Store, DBQL, AWR, `ExecutionLog3`) — the only basis for `orphan` · config table contents.
Export queries and where rules hide per artifact: `references/dw-artifact-guide.md`.

## Procedure

**0. Inventory backbone.** Load Analyzer JSON into `inventory.jsonl` (`complexity_source: "analyzer"`)
and `dependency_edges.jsonl`, locator = report row. Supplement edges the Analyzer misses (dynamic
SQL, linked servers, SSIS variables) as `kind: inferred`. No Analyzer output → build the inventory
from scripts, leave `complexity: null` (or `complexity_source: "manual"` and say so in `review.md`
and the report), and state in `review.md` that the Analyzer was not run.

**1. Units.** One coherent behaviour a reviewer holds in their head; 10–20 rules, split above ~25.
Start on the **critical path** and behind the **most-used reports**, not alphabetically.

**2. Rules from code (docs out of context).** Each rule: `logic` (verbatim), `plain` (business
language — *what*), `anchor` = named identifier + content hash (**never line numbers alone** — they
break silently on the first reformat; keep them in `locator` for convenience), `config_driven`.
Look for the classes DW code hides best: filters that are business decisions (`status <> 9`, date
windows); **join type as a rule** (`INNER JOIN dim` silently drops unmatched facts → rule *and*
finding); tie-breaks (`ROW_NUMBER … ORDER BY updated_at DESC`); `ISNULL(x,0)`; currency / unit /
timezone conversions and where the rate comes from; hard-coded lists; dynamic SQL (dependencies
hidden); cursors and full rebuilds (findings with critical-path impact); in-place `UPDATE` of
staging data before downstream reads it.

**3. Diff and assign `rule_status`.** Code wins on behaviour, documents win on intent.

| Status | Meaning | Action |
|---|---|---|
| `VERIFIED` | code and docs agree | build; no expert time |
| `CONFLICT` | disagree | top question for a domain owner |
| `CODE-ONLY` | code does it, no doc mentions it | usually the largest group; owner review or a test |
| `DOC-ONLY` | documented, not implemented in code | cut, or lives elsewhere (report filter? Excel?). Still `DOC-ONLY` when a different mechanism has a similar effect — name it in `plain`, raise a question |
| `CONFIG-ONLY` | lives in configuration data | capture the data; find who can change it |
| `DEAD` | unreachable — never scheduled, called, or read | confirm with usage log, exclude |
| `UNRESOLVED` | needs a human who knows the business | blocked; track the owner |

**4. Configuration data.** For every `config_driven` rule obtain the (masked) table content, record
effective values with a locator, and note who can change them. Check whether the code actually
*reads* the config it appears to be governed by.

**5. Dependencies, critical path, usage.** Complete edges from scheduler + code; generate the DAG
from the file. Per-step durations from job history → critical path; note full rebuilds. Usage →
`readers`, `last_read_at`; `orphan = true` **only** with a window ≥ 90 days covering a month-end and
a quarter-end — otherwise `orphan: null` + question ("year-end only?"). **Record the usage window
in `sufficiency.md`** (source, start, end, last restart if DMV-based — `dm_exec_*` resets on restart).
External consumers (ODBC/Excel, other apps) → `inventory` with `kind: external_consumer`.

**6. Findings and questions.** Silent data loss, hard-coded credentials, shared service accounts,
PII in clear text, cursors on large tables, timezone-naive timestamps, linked-server calls, double
invocations of the same load. Every `CONFLICT`, high-impact `CODE-ONLY`, ownerless `CONFIG-ONLY`,
and `orphan: null` → an open question with a named role and a default; top 3–5 to the user.

## Calibrate, then output

Before 87 procedures, do one well-documented unit, diff, have the client's expert correct it;
report the correction rate in `review.md`. Output under `runs/<run>/`: `business_rules`,
`inventory`, `dependency_edges`, `findings`, `open_questions`, `manifest.json`, `review.md` (lead
with the `rule_status` distribution — the real progress metric). The rule register tells the
Transpiler stage what to test: every `CODE-ONLY` and `CONFLICT` becomes a characterization or
reconciliation check.

## References

`../discovery-intake/references/run-layout.md` (required) · `references/dw-artifact-guide.md` —
where rules hide in T-SQL / SSIS / SQL Agent / SSRS / Informatica / Oracle / Teradata, export
queries, the month-end trap · `legacy-spec-extraction` (if installed): `rule-register.md`,
`extraction.md`, `tests.md`, `anchor_hash.py`.
