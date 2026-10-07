# Application estates — services, pipelines, APIs, dashboards

A DW estate keeps its data in a database and its rules in procedures. An application estate
spreads both across code: a service writes a file, a bus keeps every message, a log echoes a
request body, an API filters rows, a dashboard computes a number. An assessment that reads only
the "real" database misses where most of the data — and most of the rules users see — actually
are. Read this alongside `dw-artifact-guide.md` whenever the estate has application code.

## 1. Every place data lives or leaves — the data-surface inventory

Walk the code for every **write** and every **external read**, not only the configured database.
Each one is an `inventory` record (`run-layout.md`), with `holds_pii` and `erasure_reaches`:

| Surface | Where it hides | Ask |
|---|---|---|
| `table` / `file_store` — embedded databases, SQLite/DuckDB/Parquet/CSV files | a path in config, a `connect()` or `open()` in a module | who opens it, from how many processes or threads at once |
| `queue` — message buses, topics, spool files, outbox tables | producers and consumers; retention settings, or none | does a message outlive its consumer? does the payload carry personal data? |
| `log` — application logs, JSONL event logs, audit trails, error dumps | logger calls that format request or record contents | what fields are written, where to, kept how long |
| `cache` — in-memory, on-disk, Redis, memoised results, snapshots | decorators, pickles, temp dirs, CDN or HTTP caches | is it rebuilt from source, or does it keep data the source deleted? |
| `object_store` — buckets, dataset hubs, published artefacts | upload / push calls, CI steps, release scripts | public or private? versioned — does history keep deleted data? |
| `export` — files handed to people or systems, downloads, email, SFTP | report and export code, scheduled jobs | who receives it, and can it be recalled? |

`erasure_reaches`: `true` only when the code path that deletes or suppresses a subject provably
touches this surface; `false` when it provably does not; `null` + an open question otherwise. A
deletion requirement is only as complete as the least-reached surface — every `false` or `null`
on a surface with `holds_pii: true` is a finding.

## 2. The serving layer is in scope

APIs and dashboards are **consumers** (they must be re-pointed at the target) and **rule holders**
(they filter, join, round, relabel and compute). Inventory each endpoint (`api_endpoint`) and each
view, tab or chart (`ui_view`) with what it reads. Then read them as code, like report definitions:

- **Trace every displayed number and every returned field to its query.** A number that traces to
  nothing (a literal, a demo value, a placeholder) is a finding. A label that does not describe the
  data behind it is a finding.
- **Fallbacks and defaults are rules.** What does the endpoint or view return when its source fails
  or is empty — another source, cached or sample data, zero? Each fallback is a `CODE-ONLY` rule,
  and a silent one is a finding.
- **Concurrency.** A connection, handle or file shared across requests or threads; a write and a
  read of the same store from different processes without coordination — findings with the
  concurrency model named.
- **Import- and start-time side effects.** A module that opens a real store, starts a thread or
  calls the network when it is imported makes tests, workers and tooling touch production state —
  a finding (ops), and a migration hazard.
- **Filters that must match the backend.** Suppression, masking and access rules applied in the
  backend and forgotten in an endpoint or view — or the reverse — are `CONFLICT`s between layers.

## 3. Running it — `reproduced` evidence (optional, bounded)

Reading code yields `stated` findings. **Running it** — tests, a local demo, a request against a
local instance — turns a behaviour claim into a `reproduced` one, which is stronger evidence and
settles claims code reading can only suspect (races, fallbacks, stale caches).

- **Only on the project's own sample or fixture data, on this machine.** Never a client system,
  never client data, never a shared or production endpoint.
- **Ask before starting anything long-running or anything that writes outside the project folder.**
- **Record every run** in `manifest.json` `executions[]` — command, working directory, what data,
  exit code, log path — and cite the log line as the finding's locator.
- **A run that could not happen is stated, not implied**: missing runtime, missing sample data,
  no permission — `review.md` says which findings stayed unreproduced and why.
  Name the gap precisely, not the sandbox: `uv` panicking with *"thread 'main' panicked at
  system-configuration … Attempted to create a NULL object"* is uv < 0.9 consulting macOS
  SystemConfiguration while the sandbox denies `configd` (fixed upstream, astral-sh/uv #18629;
  measured: 0.8.14 panics, 0.12.23 passes under the same seatbelt) — report *"uv <version> is older
  than 0.9 and cannot run in the sandbox — upgrade uv (`curl -LsSf https://astral.sh/uv/install.sh |
  sh`)"*, never "uv crashes in this sandbox" (two live runs said that and skipped every reproduction).

Good first runs: the test suite; the app's own demo or seed script; two concurrent requests to an
endpoint suspected of sharing state; the deletion path followed by a read of every surface
marked `holds_pii`.
