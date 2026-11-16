# Config-driven flows: a metadata-driven framework read as pipelines — design

Status: for approval · 2026-11-16 · Jira VEL-1723 (epic VEL-1714) · pack `databricks-discovery` 0.12.1 → 0.13.0

## 1. Intent

Many ingestion estates are not N pipelines of code but **one generic runner and N configuration
entries**: a notebook, a Copy activity or a procedure that does the work, a list of entries that
each describe one flow (where from, where to, when, how), and a loop that calls the runner once
per entry. Read as code alone, such an estate looks like one notebook and one pipeline. The
inventory then undercounts the work, the plan and the estimate do not see the flows, and nobody
can decide flow by flow what happens to each.

The first client case (the estate VEL-1722 builds) moves most of its pipelines as configuration of
such a framework. The pack must count them — and must do it for any client, in any of the common
forms, not only the first one.

## 2. Goals

1. `legacy-etl-archaeology` recognises a metadata-driven framework in any common form: a runner, its
   entries wherever they live, and what dispatches them.
2. One `pipeline` inventory record per configured flow, with its source, target, schedule and edges.
3. The runner is its own workload record, linked to every flow it runs.
4. Every flow carries its own rationalization row (convert, rewrite, keep or retire), decided per
   runner with per-flow exceptions.
5. A flow added to the entries appears after the assessment runs again; one removed is reported.
6. The flow count and the records come from a script, never from the model.

## 3. Non-goals

- Structured schedules, activities and trigger records, and generating Lakeflow Jobs from pipeline
  records — VEL-1741 (backlog #23). This change fills `reads`, `writes` and `schedule` the way that
  work will consume them, and stops there.
- Reading a live workspace. Entries are read from exported files only (the pack reads workspaces
  GET-only or not at all).
- Any change to the desktop or to velox-spec. `desktop-databricks` says the skills underneath "change
  without a release"; `write_records.py` and the desktop reader accept unknown fields, and every
  workload record already gets convert / rewrite / retire / keep on the Scope step.
- YAML entries and entries held in code (a Python list, a dict): the agent writes those records by
  hand (§6.5), and says so.

## 4. Anti-goals — failure even if it technically works

- Anything client-specific in `skills/`, `references/` or `scripts/` (velox-skills `CLAUDE.md`).
- The model counting flows or writing flow records one by one when the script can read the entries.
- A framework whose entries could not be read presented as "0 flows" — it is the runner plus an open
  question.
- Every loop treated as a framework: a ForEach over dates, partitions or files of one dataset is a
  backfill, not N flows.
- A credential copied from a control table into a register (control tables often carry connection
  strings).

## 5. Approaches considered

| | How | Trade-off |
|---|---|---|
| **A. Instructions only** | the reference guide teaches the agent; the agent reads each entry and writes each record through `write_records.py` | least code, any form; but the count is the model's, it drifts at hundreds of entries, ids can change between runs (duplicates on a re-run), and it breaks the pack's rule that numbers come from scripts |
| **B. The model describes, a script expands** — **picked** (Bartosz, 2026-11-16) | the agent recognises the framework and writes a short description on the runner's record (where the entries are, which key is source / target / schedule, taken from the runner's code, with locators); `expand_flows.py` reads every entry and writes the records | complete and repeatable at any size, stable ids, a re-run adds exactly the new flows; costs a script, its tests and a description format. Forms the script cannot read fall back to A, labelled |
| C. Fully automatic detection by a script | a scanner finds frameworks with no model | dropped: "any form" makes heuristics brittle, and the mapping lives in the runner's code, which needs reading |

## 6. Design

### 6.1 Vocabulary

| Term | Means | Record |
|---|---|---|
| runner | the generic code that does one flow's work | its existing workload record (`notebook`, `procedure`, `pipeline`, `job`, `etl_job`), carrying `framework` |
| entry | one configuration item: a JSON file, an element of a JSON array, a JSONL line, a control-table row | — (its locator is the flow's `config_entry`) |
| flow | what one entry makes the runner do | a new `kind: pipeline` record |
| dispatcher | what loops over the entries and calls the runner (Lookup → ForEach, a `for_each` task, a cursor) | its existing workload record, if it has one; optional |

### 6.2 The description: `framework` on the runner's inventory record

The agent writes it as part of the runner's record (through `write_records.py`, as today). It is
reviewed with the runner and survives the merge into `registers/`, so a later run finds it there.

```json
"framework": {
  "entries": {"format": "json_files", "path": "sources/config/ingest/*.json"},
  "key": "flow_name",
  "fields": {"source": "source.table", "target": "{sink.schema}.{sink.table}",
             "schedule": "frequency", "load": "load_type", "enabled": "active"},
  "schedule": "daily 02:00 UTC (trigger TR_Ingest_Daily)",
  "dispatcher": "obj-0041",
  "source_id": "src-config-01",
  "evidence": [{"source_id": "src-syn-01", "locator": "sources/notebook/nb_ingest_generic.json:57",
                "excerpt": "tgt = f\"{cfg['sink']['schema']}.{cfg['sink']['table']}\"", "kind": "stated"}]
}
```

- `entries.format` ∈ `json_files` (one object per file; `path` is a glob) · `json_array` (`path` + `pointer`,
  a JSON Pointer to the list; `""` = the file is the list) · `jsonl` · `csv` (an export of a control
  table, header row = column names; optional `delimiter`). Paths are relative to the project root
  (the folder that holds `assessment/`, as every locator is) and must stay inside it.
- `entries.where` (optional) — which entries this description covers, as a list of conditions that
  all hold: `{"field": "Frequency", "equals": "H"}`, `{"field": "type", "in": ["file", "sftp"]}`,
  `{"field": "type", "not_in": ["api"]}`. It is **routing** — which dispatcher or which runner an entry
  belongs to — never the on/off switch: a dispatcher's `WHERE IsEnabled = 1` is `fields.enabled`, so a
  disabled entry is still a flow, recorded as disabled.
- `key` names the flow; it must be unique across the entries the description covers.
- `fields` values are a dotted path into the entry (`sink.table`), a CSV column, a template with
  `{dotted.path}` placeholders, or a list of those — the first that gives a non-empty value wins
  (`["source.table", "source.object"]`). Mapped: `target` (required); `source` (a table, file or
  object name) and `source_query` (SQL the runner executes) — at least one of the two; `schedule`,
  `load`, `enabled` optional. **Taken from the runner's code**, never guessed from key names in the
  entries — the evidence points at where the runner reads them.
- `schedule` (top level) is the dispatcher's schedule as text, used when the entries carry none; an
  entry's own `schedule` field wins.
- `dispatcher` is the dispatcher's inventory id, or null.
- `source_id` is the registered source the entries come from (the manifest's).

`framework` may also be a **list** of such descriptions on one runner — one per dispatcher, each with
its own `where`, `dispatcher` and `schedule` (one control table read by an hourly and a daily
pipeline). A runner fed only part of the entries (a Switch on `item().type` sending some entries to
runner A and the rest to runner B) carries a description with its own `where` on each runner.

### 6.3 `expand_flows.py expand <run-dir> <runner-id> [--root …] [--registers …]`

Stdlib, Python 3.9+, in a new `legacy-etl-archaeology/scripts/`; it validates through
`discovery-intake/scripts/write_records.py` (imported by path, run where it is). Defaults:
`--root` = the run dir's fourth parent (`<root>/assessment/<project>/runs/<run>`), `--registers` =
`assessment/<project>/registers/`. The runner's record is taken from the run's `inventory.jsonl`,
else from the registers.

Per entry it writes:

- **inventory** — `id` `<runner-id>-<slug(key)>` (lower-case, runs of other characters → `-`, no
  length cap; two entries whose keys give one slug — they differ only in case or punctuation —
  refuse the whole expansion, naming both), `kind: pipeline`,
  `name` = the key's value, `system` = the runner's, `runner`, `config_entry` (locator: `file:line`
  of the key in that file, or `export.csv:<line>`), `reads: [source]` (empty when the flow reads by
  query), `source_query` (the SQL verbatim, when mapped), `writes: [target]` (names as
  the entry states them — what VEL-1741 needs to build a task), `schedule`, `load`, `enabled`
  (`true`/`false` from the usual truthy and falsy spellings, else `null`), `evidence` (that locator,
  kind `stated`, excerpt built as `<key>=<value>` — never the raw line), and a generated `meaning`
  ("Flow orders_daily run by nb_ingest_generic: erp.orders → bronze.orders"; "by query" in place of a
  source; cut to 160).
- An entry missing its target, or both source and source query, is still written — the count stays
  true — with what it has, and listed as **incomplete**. The script does not parse SQL: a query's
  tables are left to the reviewer, and the summary lists the flows that read by query.
- **dependency_edges** — flow → runner `calls`; dispatcher → flow `triggers` (when a dispatcher is
  named; evidence = the description's); flow → object `reads` / `writes` when an inventory record
  (run or registers) matches the source or target by name (case-insensitive, whole name or a
  dot-bounded suffix, as the desktop's rule matching does). Each with a generated `meaning`.

It skips an entry with no key value (a template or defaults file) and lists it. It refuses a
`fields` value that names a credential (the `write_records` credential key pattern), and a path
that leaves the root. With a list of descriptions, an entry two of them both cover is refused
(their `where` overlap). Re-running replaces by id (write_records' upsert), so a new entry adds one
record and a changed one replaces its own.

**Output is deterministic**: the same entries give byte-identical records (fixed key order, entries
in sorted path / line order, no timestamps). The desktop keeps a reviewed decision while the new
run's copy hashes the same as the reviewed one, and treats a key the latest run does not produce as
gone — so every run expands every framework again, and an unchanged flow must not look changed.

It prints a summary for `review.md` and the manifest: flows written (+new / replaced), disabled,
incomplete and query-read flows, source and target names with no inventory match, **gone** — records
with this `runner` in the run or the registers whose entry no longer exists (not deleted; the
reviewer rejects them), and the files it read.

### 6.4 `expand_flows.py decide <run-dir> <runner-id> <disposition> [--except <flow-id>=<disposition> …]`

Writes the rationalization rows of one framework in one go (used by `assessment-synthesis`).
`<disposition>` is any workload disposition, with the Scope step's meanings:

- every flow: the default, or its exception. **convert** = translated as it is: the entry carried as
  configuration of a generic Databricks runner (target_component
  `"generic Databricks runner — entry <key>"`); **rewrite** = redesigned as native Databricks
  ingestion (`"<catalog>.bronze.<target> (native ingestion)"`, a placeholder); **keep** = stays where
  it runs (e.g. the copy stays in Data Factory and lands where Databricks reads it); **retire**. A
  disabled flow → `retire` whatever the default, with a note that the owner confirms it.
- the runner and the dispatcher: `convert` when any flow is convert, `keep` when any flow is keep
  and none convert, else `retire`.

**Which default to recommend** — §8a.

### 6.5 What the agent does (`legacy-etl-archaeology`)

New step **0c. Metadata-driven frameworks**, and a new `references/framework-guide.md`:

1. **Recognise.** Signs: one runner called with an entry or `item()` as its parameter from a loop
   (Lookup → ForEach → notebook / Copy, a `for_each` task, a cursor over a config table running
   dynamic SQL); a folder of similar config files; a control table whose rows name sources and
   targets. The guide's table covers the common forms (config files + notebook; a control table +
   Lookup/ForEach + Copy; a config table + procedure; a Databricks `for_each` / onboarding-file
   pipeline; a list in code). A loop over dates, partitions or one dataset's files is not one.
2. **Describe.** Read the runner's code for the keys it actually reads; write `framework` on the
   runner's record with locators. Entries in a table need its exported content (already a pack
   input, "config table contents"); not in hand → a source request line and an open question.
3. **Expand.** Run `expand_flows.py expand`; never count or write the flows yourself. Put its
   summary in `review.md` (disabled, unmatched, gone) and its files in the manifest.
4. **Fallback.** A form the script cannot read (YAML, entries in code): write the flow records by
   hand in the same shape, and say in `review.md` which framework and why. Entries not in hand: the
   runner, the dispatcher and an open question ("where are the entries?") — never a count.

`dw-artifact-guide.md`'s Synapse section gets one line pointing a ForEach-over-one-runner pipeline
to the guide. `run-layout.md` documents the new fields (`framework`, `runner`, `config_entry`, `load`,
`enabled`, `source_query`). `assessment-synthesis` gets the flow rule (§6.4: decide per runner with
exceptions, through the script) and these deliverable changes in `build_deliverables.py`:

- **Dispositions per layer.** Today it knows only `migrate / modernize / retire / defer`, so every
  workload's `convert / rewrite / keep` counts as undecided — the §9 headline would read 200 flows
  marked convert as "0% decided", and the kind × disposition table and the Summary sheet leave them
  out. It learns the three layers' words (`write_records.DISPOSITIONS`): decided = any disposition but
  `defer` or none; the kind × disposition table takes the words its kinds use; the Summary counts
  every word. This fixes procedures and jobs too, not only flows.
- **A framework is one row in the report, every flow a row in the workbook.** The §4 workload
  catalogue (40-row cap), the §9 per-object table (30) and the §10 component mapping (30) show a
  runner's flows as one row — "nb_ingest_generic — 7 flows: 5 convert, 1 rewrite, 1 retire (disabled)"
  — so the caps go to the objects a reader decides one by one. The workbook's Inventory sheet gains a
  `runner` column; its Rationalization sheet keeps one row per flow.

### 6.6 Tests and evals

- `legacy-etl-archaeology/scripts/test_expand_flows.py` (pytest, picked up by the CLAUDE.md loop):
  each format; dotted paths, templates and first-non-empty lists; truthy/falsy `enabled`; `where`
  (equals, in, not_in) and a list of descriptions, overlap refused; query-read flow (`source_query`,
  empty `reads`); incomplete entry written and listed; stable ids and byte-identical output across
  runs; slug collision refused; keyless entry skipped and listed; re-run with one entry added (+1 new,
  the rest replaced, no duplicate) and one removed (listed as gone); edges matched by name; credential
  field and escaping path refused; every written record passes `write_records` validation; `decide`
  rules (default, exception, disabled → retire, runner and dispatcher follow).
- `assessment-synthesis/scripts/test_build.py`: workload dispositions count as decided; a framework
  is one row in §4, §9 and §10 and one row per flow in the workbook; the Inventory sheet's `runner`
  column.
- Two synthetic fixtures, each with `README.md` and `TRAPS.md`, and an `evals.json` case each:
  - **`framework-config-files`** — a Synapse Git export: a pipeline listing a config folder and
    calling one notebook per file in a ForEach, the notebook, a daily trigger, seven entries (one
    inactive, one with a query instead of a table) and a template file with no key. Traps: entries
    carry a legacy `target_table` key the notebook never reads (the mapping must come from the code);
    an ordinary procedure pipeline beside it must not be expanded.
  - **`framework-control-table`** — the "metadata-driven copy" form: one control table read by two
    pipelines, hourly and daily, each a Lookup (`WHERE Frequency = 'H' AND IsEnabled = 1`, and `'D'`)
    → ForEach → Copy with the item's query and sink, each with its trigger; the table's DDL and its
    exported rows (ten, two disabled). Traps: `IsEnabled` is the on/off switch, not routing (disabled
    rows are flows, recorded as disabled); a legacy `TargetTable_Old` column nothing reads; two rows
    loading the same target (a finding); a connection-string column whose value must not reach a
    register.
- The first client estate (VEL-1722) is the acceptance run once it exists; nothing from it enters
  the repo.

### 6.7 Versions

Pack 0.12.1 → 0.13.0; `legacy-etl-archaeology` 0.3.0 → 0.4.0; `assessment-synthesis` 0.5.1 → 0.6.0;
`discovery-intake` 0.7.2 → 0.7.3 (run-layout only). The desktop picks the pack up with its existing
`scripts/sync-velox-skills.mjs`, in its own change.

## 7. Acceptance (VEL-1723)

| Criterion | Proved by |
|---|---|
| each configured flow is a pipeline record with source, target, schedule and edges | unit tests; evals 6 and 7; the VEL-1722 estate when it exists |
| the runner is linked to each flow | `calls` edges — unit tests, evals |
| a disposition per flow (convert / rewrite / keep / retire) | `decide` — unit tests; eval assertions on synthesis (§8a) |
| a flow added to the entries appears after a re-run | re-run unit test |
| a second form gives the same records | the control-table fixture and eval 7 |

## 8. Calls made here, for the reviewer to check

- The ticket's "convert or keep" is read with the Scope step's words: convert = translated as it is
  (the entry carried as configuration), rewrite = native ingestion, keep = stays where it runs. All
  four workload dispositions stay available per flow.
- `reads` / `writes` hold names as configured; edges hold ids, only where an object matches. A query
  is kept verbatim in `source_query` and not parsed.
- The description lives on the runner's record, not in a separate file (the run layout allows no new
  files, and the record is reviewed and merged with the runner). One runner may carry several, with
  `where` routing; overlapping descriptions are refused rather than double-counted.
- Ids carry the whole key, no length cap; a collision is refused, never hashed (a hash added later
  would mark every reviewed flow gone and new).
- Gone flows are reported, not deleted. An incomplete entry is written and listed, not dropped.
- A disabled flow is a record (`enabled: false`) and a retire candidate, not omitted.
- YAML and entries in code are the labelled fallback, not script formats, in this change.
- `build_deliverables.py` learns every layer's dispositions (a fix that also helps procedures and
  jobs), and the report collapses a framework's flows into one row in §4, §9 and §10; the workbook
  keeps one row per flow.

### 8a. Which default `assessment-synthesis` recommends for a framework (agreed, Bartosz, 2026-11-16)

By what the runner is:

- **Code that can run on Databricks** (a PySpark or Python notebook, a Python script): default
  **convert** — carry the entries as configuration and move the runner; the cheapest faithful path.
- **A service-bound activity** (a Data Factory / Synapse Copy, SSIS): there is no runner to move, so
  default **rewrite** to native ingestion, with **keep** named in the recommendation's reason when the
  copy can stay and land where Databricks reads it.
- **A procedure with dynamic SQL**: default **convert** (the procedure is translated like any other).
- Per-flow exceptions only with evidence: a finding on the flow, a source Lakeflow Connect supports
  where the framework's own handling is the weak part, a disabled entry (→ retire).

Evals 6 and 7 assert this rule's outcome (convert for the notebook framework, rewrite for the Copy
framework).

## 9. Left to the builder

Function and module structure inside `expand_flows.py`; the exact wording of the guide and of
generated `meaning` lines within their budgets; fixture names and contents beyond the traps listed;
the eval assertion wording.
