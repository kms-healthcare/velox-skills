# Metadata-driven frameworks — one pipeline per configured flow

Many ingestion estates are not N pipelines of code but **one generic runner and N configuration
entries**. Read as code alone, such an estate is one notebook and one loop, and the inventory
undercounts the work by the number of entries: the plan, the estimate and the Scope step never see
the flows. This guide makes each entry its own `pipeline` record — counted by
`scripts/expand_flows.py`, never by you.

## 1. What a framework is

| Part | Is | Record |
|---|---|---|
| **runner** | the generic code that does one flow's work | its own workload record (`notebook`, `pipeline`, `procedure`, `job`, `etl_job`), carrying `framework` (§3) |
| **entry** | one configuration item: a JSON file, an element of a JSON array, a JSONL line, a control-table row | none — its locator is the flow's `config_entry` |
| **flow** | what one entry makes the runner do | one `kind: pipeline` record, written by the script |
| **dispatcher** | what loops over the entries and calls the runner | its own workload record, if it has one |

## 2. Recognise it

The sign is always the same: **one runner called with an entry (`item()`, a row, a file) as its
parameter, from a loop over a list someone maintains as data.**

| Form | Entries | Dispatcher | Runner |
|---|---|---|---|
| config files + notebook | a folder of JSON files (`config/ingest/*.json`) | GetMetadata `childItems` → ForEach → SynapseNotebook / DatabricksNotebook | the notebook |
| "metadata-driven copy" (Data Factory, Synapse) | rows of a control table | Lookup → ForEach → Copy, or → ExecutePipeline of a parameterised child | the Copy, or the child pipeline |
| config table + procedure | rows of a config table | a cursor or `WHILE` loop in a procedure, dynamic SQL per row | the procedure, or the dynamic statement it builds |
| Databricks | an onboarding JSON/YAML, a task-values list | a job's `for_each` task, a pipeline generated from metadata | the notebook or pipeline the loop runs |
| in code | a list or dict in a script | a `for` loop | the function it calls |

**Not a framework:** a loop over dates or partitions (a backfill), over the files of one dataset, or
over retries. Those are one flow, however many iterations it runs. Ask: would a business owner name
each iteration as a separate feed? If not, it is one pipeline.

A pipeline whose Lookup or ForEach feeds a framework is the dispatcher, not a flow; record it once.

## 3. Describe it — `framework` on the runner's record

Write it as part of the runner's inventory record, through `write_records.py` as usual. It is
reviewed with the runner and merged with it, so the next run finds it in `registers/`.

```json
"framework": {
  "entries": {"format": "json_files", "path": "sources/config/ingest/*.json"},
  "key": "flow_name",
  "fields": {"source": "source.table", "source_query": "source.query", "target": "{sink.schema}.{sink.table}",
             "load": "load_type", "enabled": "active"},
  "schedule": "daily 02:00 UTC (trigger TR_Ingest_Daily)",
  "dispatcher": "obj-0002",
  "source_id": "src-config-01",
  "evidence": [{"source_id": "src-syn-01", "locator": "sources/notebook/nb_ingest_generic.json:60",
                "excerpt": "schema, table = cfg[\"sink\"][\"schema\"], cfg[\"sink\"][\"table\"]", "kind": "stated"}]
}
```

- `entries.format`:
  - `json_files`: one object per file, `path` is a glob.
  - `json_array`: `path` + `pointer`, a JSON Pointer to the list (`""` = the file is the list).
  - `jsonl`.
  - `csv`: a control table's export, with a header row and an optional `delimiter`.
  - Paths are relative to the project root and stay inside it.
- `key` names the flow. It must be unique; the flow's id is `<runner id>-<key, slugged>`.
- `fields` values are one of:
  - a dotted path (`sink.table`) or a CSV column;
  - a template with `{dotted.path}` placeholders;
  - a list of those, where the first that gives a value wins.

  `target` is required, and so is `source` (a table, file or object) or `source_query` (SQL the runner
  executes). `schedule`, `load` and `enabled` are optional.
- **`target` is the table the flow lands, `<schema>.<table>`** (`{SinkSchema}.{SinkTable}`), even when
  the runner writes files into a lake folder `<schema>/<table>`: the folder is that table's storage,
  and inventory names and the rationalization match tables. The path stays in the `evidence`.
- **The mapping comes from the runner's code, never from the key names in the entries.** Read which
  keys the runner actually reads. An entry often carries keys nothing reads, such as a legacy target
  or a column kept from an earlier version, and mapping one of those writes wrong targets with full
  confidence. The `evidence` points at where the runner reads them.
- `schedule` is the dispatcher's schedule as text, taken from its trigger, for entries that carry
  none. An entry's own schedule field wins.
- `entries.where` is **routing**: which entries this description covers. Each condition has a `field`
  and one of `equals`, `in` or `not_in`, and all of them must hold. Use it when one table feeds several
  dispatchers (`Frequency = 'H'` hourly, `'D'` daily), or when a dispatcher sends entries to different
  runners by type. Then write **a list of descriptions**: one per dispatcher, each with its own
  `where`, `dispatcher` and `schedule`, or one on each runner.
- **Check that the `where` clauses cover every entry.** Read the values the routing field takes in
  the entries (every `Frequency` in the table, not only the ones the dispatchers you found read). An
  entry no description covers, on this runner or another over the same entries, is no flow: the
  script reports it as `unrouted`. A `'W'` row beside `'H'` and `'D'` dispatchers is a dispatcher you
  have not found, or a row nothing runs; ask.
- **The on/off switch is `fields.enabled`, never `where`.** A dispatcher's `WHERE IsEnabled = 1` means
  a disabled row does not run. It is still a flow: recorded as disabled, and a retire candidate whose
  owner confirms. Put it in `where` and it disappears from the count.

## 4. Expand it

From this skill's directory:

```bash
python3 "<directory>/scripts/expand_flows.py" expand <run-dir> <runner-id>
```

Run it where it is, never copied. It reads every entry and writes:

- one `pipeline` record per flow into the run's `inventory.jsonl`, with `runner`, `config_entry`,
  `reads`, `source_query`, `writes`, `schedule`, `load`, `enabled` and a `meaning`;
- the flow's edges: `calls` to the runner, `triggers` from the dispatcher, and `reads` / `writes` to an
  inventory object whose name matches.

Every record passes through `write_records.py`. **Never count flows yourself, and never write flow
records by hand when the script can read the entries.** A number in `review.md` or the report comes
from the script's summary, which prints as JSON. Each list in it is its `count` and its `first`
ten items, however many flows the framework has. Write each list **once** in `review.md`: its count
and those ten, never an item per flow. 5,000 rows once gave 11,667 review items. The workbook keeps
every flow.

| Summary key | Goes to |
|---|---|
| `flows`, `new`, `replaced` | `review.md` — the count |
| `disabled` | `review.md`; retire candidates — one open question to the runner's owner for all of them, with the count and the first ten |
| `incomplete` | `review.md`; an entry with no target, or no source or query — a question |
| `by_query` | `review.md`; the tables a query reads are left to the reviewer, unparsed |
| `unmatched`, `ambiguous` | `review.md`; a source or target with no (or several) inventory objects — add the object, or raise a question |
| `unrouted` | `review.md`; entries no description routes, so no flow — an open question asking who runs them. When several runners read one table, the one with the lowest id lists them |
| `skipped` | `review.md`; files with no key value (templates, defaults) |
| `gone` | `review.md`; flows whose entry no longer exists — the reviewer rejects them, nothing is deleted, and `decide` gives them no decision. `decide`'s `gone_decided` names those that already had one: the reviewer rejects the flow and its decision together |
| `files` | `manifest.json` sources, in full |

Expand again on every run, even when nothing changed. The desktop keeps a reviewed decision only
while the run's copy is unchanged, and the script writes the same bytes for the same entries.

## 5. Fallback

- **A form the script cannot read** (YAML, entries held in code): write the flow records by hand in
  the same shape, with the same id rule. Say in `review.md` which framework was written by hand and
  why.
- **Entries not in hand** (a control table never exported, a config folder in a lake you cannot
  read): record the runner and the dispatcher, add a line to `source_request.md` ("contents of
  `<table>` / `<folder>`"), and raise an open question. **Never a count.** A framework is never
  "0 flows", and the script refuses one.

## 6. Secrets

Control tables often carry connection strings, users and passwords in a column. **Never map one.**
The script refuses a `fields` value that names a credential, and copies only the columns you map.
Excerpts are built as `<key>=<value>`, never from the raw row.
