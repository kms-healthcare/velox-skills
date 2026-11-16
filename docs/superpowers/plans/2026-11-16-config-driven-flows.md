# Config-driven flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `databricks-discovery` pack reads a metadata-driven framework (a runner, its configuration entries, a dispatcher) as one `pipeline` record per configured flow, decides each flow's disposition per runner, and reports a framework as one row.

**Architecture:** The agent recognises the framework and writes a `framework` description on the runner's inventory record; a stdlib script `expand_flows.py` (in `legacy-etl-archaeology/scripts/`) reads every entry and writes flow records and edges through `write_records.py` (`expand`), and writes the rationalization rows of one framework (`decide`). `build_deliverables.py` learns every layer's dispositions and collapses a framework's flows in the report. Skill text, two synthetic fixtures and two eval cases teach and test the agent's half.

**Tech Stack:** Python 3.9+ stdlib (scripts), pytest-compatible plain test functions, openpyxl (workbook only), Markdown skills.

**Spec:** `docs/superpowers/specs/2026-11-16-config-driven-flows-design.md` (approved 2026-11-16).

## Global Constraints

- Scripts are stdlib only and run on Python 3.9+: start each with `from __future__ import annotations`; no `match`, no runtime `X | Y`.
- A pack script runs by its path where it is, never copied. `expand_flows.py` imports `write_records` from `HERE.parents[1] / "discovery-intake" / "scripts"` (`HERE` = its own folder).
- Records reach a register only through `write_records.write()`. Every record is checked with `write_records.problems()` first, and one refusal writes nothing.
- Nothing client-specific in `skills/`, `references/`, `scripts/` or `evals/fixtures/`. Use synthetic names only: the fixtures use the made-up company "Lumen Freight", never a real client.
- Locators are relative to the project root (the folder holding `assessment/`) and always use `/`. `evidence[].excerpt` is at most 120 characters, and `meaning` is at most 160 (cut to 159 + `…`).
- Skills and references are written in English.
- Test command, run inside a scripts folder: `uv run -q --no-project --with pytest --with openpyxl python -m pytest -q <file>`. `test_build.py` is module-level, so run it as `uv run -q --no-project --with openpyxl python test_build.py`.
- Commit the paths you touched by name, never `git add -A`, and never push. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Done means the velox-skills CLAUDE.md loop is green: `for d in databricks-discovery/skills/*/scripts; do (cd "$d" && uv run -q --no-project --with pytest --with openpyxl python -m pytest -q); done`, plus `python test_build.py`.

## Review Focus

These are the inputs the spec implies but does not name, ordered by how likely they are to bite. Each one has its test pinned in the task that owns the code:

1. **Exported files with a UTF-8 BOM** (Synapse Studio JSON, SSMS CSV). They must read as if there were no BOM, and the first CSV column's name must stay clean. Task 1, `test_read_entries_each_format`.
2. **A path or glob that matches nothing.** It must be refused with "no entries", never reported as "0 flows". Task 1, `test_read_entries_refusals`.
3. **A Windows-style path in the description** (`sources\config\*.json`). It must still be read, and its locators must use `/`. Task 1, `test_read_entries_each_format`.
4. **Numeric key values** (a control table's `FlowId` 17). The name must be `"17"` and the id `<runner>-17`. Task 2, `test_numeric_key`.
5. **An unmapped control-table column holding a connection string.** Its value must never reach a record. Task 2, `test_descriptions_route_entries_and_refuse_overlap`.

---

## File map

| File | Responsibility |
|---|---|
| `databricks-discovery/skills/legacy-etl-archaeology/scripts/expand_flows.py` (new) | read entries, build flow records and edges (`expand`), framework rationalization (`decide`), CLI |
| `…/legacy-etl-archaeology/scripts/test_expand_flows.py` (new) | its tests, plus the two fixture checks |
| `…/assessment-synthesis/scripts/build_deliverables.py` | layer dispositions, framework rows in §4/§9/§10, Inventory `runner` column |
| `…/assessment-synthesis/scripts/test_build.py` | a framework block |
| `…/legacy-etl-archaeology/references/framework-guide.md` (new) | how the agent recognises, describes, expands, falls back |
| `…/legacy-etl-archaeology/SKILL.md`, `references/dw-artifact-guide.md` | step 0c; Synapse pointer |
| `…/discovery-intake/references/run-layout.md` | new fields |
| `…/assessment-synthesis/SKILL.md`, `references/report-template.md` | §1c frameworks and the §8a rule; report sections 4/9/10 |
| `README.md`, `databricks-discovery/.claude-plugin/plugin.json`, three `SKILL.md` versions | docs and versions |
| `databricks-discovery/evals/fixtures/framework-config-files/`, `…/framework-control-table/` (new), `evals/evals.json` | fixtures and evals 6, 7 |

---

### Task 1: Read a framework's entries

**Files:**
- Create: `databricks-discovery/skills/legacy-etl-archaeology/scripts/expand_flows.py`
- Test: `databricks-discovery/skills/legacy-etl-archaeology/scripts/test_expand_flows.py`

**Interfaces:**
- Produces (in `expand_flows.py`):
  - `write_records` — the imported module.
  - `FORMATS = ("json_files", "json_array", "jsonl", "csv")`
  - `class Entry(NamedTuple): data: dict; path: str; line: int` — `path` is root-relative and uses `/`.
  - `get_path(entry: dict, dotted: str) -> Any` — tries a flat key equal to `dotted` first, then walks the dots. Returns `None` when the path is missing.
  - `resolve(entry: dict, spec, raw: bool = False) -> Any`:
    - `spec` is a dotted path, a template with `{dotted.path}` placeholders, or a list of those where the first non-empty result wins.
    - With `raw=False` the result is a `str` or `None`; empty strings become `None`, and numbers become `str`.
    - A template whose placeholder is missing gives `None`.
    - With `raw=True` the value comes back untouched (used for `enabled`; templates not allowed).
  - `truthy(value) -> Optional[bool]`
  - `matches(entry: dict, where: list) -> bool` — conditions are `{"field", "equals"|"in"|"not_in"}`, all of which must hold. Values are compared as `str`.
  - `slug(key: str) -> str` — lower-case, with runs of `[^a-z0-9]` replaced by `-` and stripped from both ends.
  - `read_entries(root: Path, spec: dict, key: str) -> list[Entry]`:
    - Entries are sorted by `(path, line)`.
    - `spec` is `framework.entries`. Its `where` is applied by the caller, not here.
    - A refusal raises `SystemExit(<message>)`.

- [ ] **Step 1: Write the failing tests.** Create `test_expand_flows.py` with the shared helpers and the tests below. Each later task appends to this file.

```python
"""python3 test_expand_flows.py — offline self-check of expand_flows.py."""
import json
import tempfile
from pathlib import Path

import expand_flows as x

w = x.write_records
EV = [{"source_id": "src-01", "locator": "sources/nb.json:3", "excerpt": "cfg['sink']", "kind": "stated"}]


def cfg(**kv):
    return json.dumps(kv, indent=2)


def assert_refused(fn, msg):
    try:
        fn()
    except SystemExit as e:
        assert msg in str(e), e
    else:
        raise AssertionError(f"not refused: {msg}")


def test_resolve_paths_templates_and_alternatives():
    e = {"source": {"table": None, "query": "SELECT 1"}, "sink": {"schema": "bronze", "table": "orders"}, "Sink.Table": "flat"}
    assert x.resolve(e, "sink.table") == "orders"
    assert x.resolve(e, "{sink.schema}.{sink.table}") == "bronze.orders"
    assert x.resolve(e, ["source.table", "source.query"]) == "SELECT 1"
    assert x.resolve(e, "Sink.Table") == "flat"                       # a flat key with a dot wins over walking
    assert x.resolve(e, "{sink.schema}.{missing}") is None
    assert x.resolve(e, "source.table") is None
    assert x.resolve({"id": 17}, "id") == "17"
    assert x.resolve({"on": 0}, "on", raw=True) == 0


def test_truthy_and_where():
    assert [x.truthy(v) for v in (True, 1, "1", "Yes", " true ", "Y", "on")] == [True] * 7
    assert [x.truthy(v) for v in (False, 0, "0", "no", "FALSE", "n", "off")] == [False] * 7
    assert [x.truthy(v) for v in (None, "", "maybe", 2)] == [None] * 4
    e = {"Frequency": "H", "type": "file", "n": 1}
    assert x.matches(e, []) and x.matches(e, [{"field": "Frequency", "equals": "H"}])
    assert not x.matches(e, [{"field": "Frequency", "equals": "D"}])
    assert x.matches(e, [{"field": "type", "in": ["file", "sftp"]}, {"field": "n", "equals": "1"}])
    assert not x.matches(e, [{"field": "type", "not_in": ["file"]}])
    assert x.slug("Erp Customers!") == "erp-customers" and x.slug("17") == "17"


def entry_files(root):
    (root / "c").mkdir()
    (root / "c/b.json").write_text('{\n  "name": "b",\n  "src": "s.b"\n}', encoding="utf-8")
    (root / "c/a.json").write_bytes('﻿{\n  "x": 1,\n  "name": "a"\n}'.encode("utf-8"))      # BOM, as exports carry
    (root / "flows.json").write_text('{"flows": [\n  {"name": "f1"},\n  {"name": "f2"}\n]}')
    (root / "f.jsonl").write_text('{"name": "l1"}\n\n{"name": "l2"}\n')
    (root / "ctl.csv").write_bytes('﻿Name;Src\nr1;s.r1\n"r2";"multi\nline"\nr3;s.r3\n'.encode("utf-8"))


def test_read_entries_each_format():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        entry_files(root)
        e = x.read_entries(root, {"format": "json_files", "path": "c/*.json"}, "name")
        assert [(i.path, i.line, i.data["name"]) for i in e] == [("c/a.json", 3, "a"), ("c/b.json", 2, "b")]
        e = x.read_entries(root, {"format": "json_files", "path": "c\\*.json"}, "name")       # a Windows-style path
        assert [i.path for i in e] == ["c/a.json", "c/b.json"]
        e = x.read_entries(root, {"format": "json_array", "path": "flows.json", "pointer": "/flows"}, "name")
        assert [(i.line, i.data["name"]) for i in e] == [(2, "f1"), (3, "f2")]
        e = x.read_entries(root, {"format": "jsonl", "path": "f.jsonl"}, "name")
        assert [(i.line, i.data["name"]) for i in e] == [(1, "l1"), (3, "l2")]
        e = x.read_entries(root, {"format": "csv", "path": "ctl.csv", "delimiter": ";"}, "Name")
        assert [(i.line, i.data["Name"]) for i in e] == [(2, "r1"), (3, "r2"), (5, "r3")]   # r2's quoted newline: r3 starts on 5
        assert list(e[0].data) == ["Name", "Src"]                                          # no BOM in the first column's name


def test_read_entries_refusals():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        entry_files(root)
        (root / "list.json").write_text("[1, 2]")
        for spec, msg in (({"format": "yaml_files", "path": "c/*.yaml"}, "format"),
                          ({"format": "json_files", "path": "nothing/*.json"}, "no entries"),
                          ({"format": "json_files", "path": "../outside/*.json"}, "outside the project"),
                          ({"format": "json_files", "path": "/etc/*.json"}, "outside the project"),
                          ({"format": "json_files", "path": "list.json"}, "one object per file"),
                          ({"format": "json_array", "path": "flows.json", "pointer": "/nope"}, "pointer")):
            assert_refused(lambda: x.read_entries(root, spec, "name"), msg)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
```

- [ ] **Step 2: Run the tests to verify they fail.**
Run: `cd databricks-discovery/skills/legacy-etl-archaeology/scripts && uv run -q --no-project --with pytest python -m pytest -q test_expand_flows.py`
Expected: an ERROR at collection, `ModuleNotFoundError: No module named 'expand_flows'`.

- [ ] **Step 3: Implement the Task 1 interfaces in `expand_flows.py`.**
  - Module docstring:
    - the usage of both subcommands (the CLI comes in Task 2);
    - why a script: "the flow count comes from a script, never from the model";
    - "Stdlib only."
  - Reading files: open everything with `encoding="utf-8-sig"`. A path's `\` becomes `/`.
  - Path checks: refuse an absolute path and any `..` segment with "… is outside the project root". Expand globs with `sorted(root.glob(pattern))`. No match gives "no entries at <path> — check the path; a framework is never 0 flows".
  - Lines for `json_files` and `json_array`:
    - Search the file's lines for `"<last segment of key>"\s*:\s*"?<re.escape(str(value))>`.
    - In an array, start the search after the previous entry's line.
    - When nothing is found, use line 1.
  - Lines for `jsonl`: the 1-based number of each non-blank line.
  - Lines for `csv`: use `csv.DictReader` (optional `delimiter`). An entry's line is the previous `reader.line_num + 1`, with the header on line 1.
  - Unknown format: "format '<f>' is not one of json_files / json_array / jsonl / csv — write the flows by hand (framework-guide.md, fallback)".
  - Wrong file shape: a non-object file under `json_files` gives "one object per file — use json_array". A pointer that is missing or not a list gives "pointer '<p>' does not name a list in <path>".

- [ ] **Step 4: Run the tests to verify they pass.**
Run: the Step 2 command.
Expected: `4 passed`.

- [ ] **Step 5: Commit.**
```bash
git add databricks-discovery/skills/legacy-etl-archaeology/scripts/expand_flows.py databricks-discovery/skills/legacy-etl-archaeology/scripts/test_expand_flows.py
git commit -m "databricks-discovery: expand_flows.py reads a framework's entries (VEL-1723)"
```

---

### Task 2: `expand` — one pipeline record per entry, edges, summary, CLI

**Files:**
- Modify: `…/legacy-etl-archaeology/scripts/expand_flows.py`
- Test: `…/legacy-etl-archaeology/scripts/test_expand_flows.py` (append)

**Interfaces:**
- Consumes: Task 1's `read_entries`, `resolve`, `truthy`, `matches`, `slug`, `write_records`.
- Produces:
  - `expand(run_dir: Path, runner_id: str, root: Optional[Path] = None, registers: Optional[Path] = None) -> dict`:
    - Defaults: `root` is `run_dir.parents[3]`, and `registers` is `run_dir.parents[1] / "registers"`.
    - Writes `inventory` and `dependency_edges` in `run_dir`.
    - Returns these keys, every list sorted: `runner, flows, new, replaced, disabled, incomplete, by_query, unmatched, ambiguous, skipped, gone, files`.
  - `inventory_of(run_dir: Path, registers: Path) -> dict[str, dict]` — the run's inventory over the registers', the run winning, rejected records left out. Used by `decide` too.
  - CLI `main(argv: Optional[list] = None)`: `expand <run-dir> <runner-id> [--root R] [--registers G]`. It prints the summary as `json.dumps(..., indent=2, ensure_ascii=False)`.
  - A flow record has these keys, in this order:
    - `id`, `kind`, `name`, `system`, `runner`, `config_entry`, `reads`, `source_query`, `writes`, `schedule`, `load`, `enabled`, `meaning`, `evidence`.
    - Values are `None` when not mapped.
  - Edge kinds:
    - `calls`: flow → runner;
    - `triggers`: dispatcher → flow;
    - `reads` / `writes`: flow → object.
    - Each edge carries `evidence` and `meaning`.

- [ ] **Step 1: Write the failing tests.** Append the helpers and tests below.

```python
def project(tmp, files, framework, runner_extra=None, inventory=()):
    """A project root holding `files`, and a run whose inventory has the runner obj-0001 (carrying `framework`) and `inventory`."""
    root = Path(tmp)
    for p, text in files.items():
        f = root / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    run = root / "assessment" / "proj" / "runs" / "2026-11-16_run-01"
    runner = {"id": "obj-0001", "kind": "notebook", "name": "nb_ingest", "system": "SYS-1", "evidence": EV,
              "meaning": "the generic ingestion notebook", "framework": framework, **(runner_extra or {})}
    w.write(run, "inventory", [runner, *inventory])
    return root, run


def fw(**kw):
    base = {"entries": {"format": "json_files", "path": "sources/config/*.json"}, "key": "name",
            "fields": {"source": "src", "target": "tgt"}, "schedule": "daily 02:00", "dispatcher": None,
            "source_id": "src-cfg", "evidence": EV}
    base.update(kw)
    return base


def rows(run, register):
    return [json.loads(l) for l in (run / f"{register}.jsonl").read_text().splitlines()]


def obj(i, kind, name):
    return {"id": i, "kind": kind, "name": name, "system": "SYS-1", "evidence": EV, "meaning": name}


def test_expand_writes_flows_and_edges():
    with tempfile.TemporaryDirectory() as d:
        files = {"sources/config/orders.json": cfg(name="erp_orders", src="erp.dbo.Orders", tgt="bronze.orders", active="1"),
                 "sources/config/custs.json": cfg(name="Erp Customers", src="erp.dbo.Customers", tgt="bronze.customers", active=0),
                 "sources/config/q.json": cfg(name="by_query", query="SELECT * FROM erp.dbo.Lines", tgt="bronze.lines"),
                 "sources/config/_defaults.json": cfg(active=True)}
        root, run = project(d, files, fw(fields={"source": "src", "source_query": "query", "target": "tgt", "enabled": "active"},
                                         dispatcher="obj-0002"),
                            inventory=[obj("obj-0100", "table", "[bronze].[orders]"), obj("obj-0002", "pipeline", "PL_Ingest_All")])
        s = x.expand(run, "obj-0001")
        inv = {r["id"]: r for r in rows(run, "inventory")}
        assert (s["flows"], s["new"], s["replaced"]) == (3, 3, 0)
        o = inv["obj-0001-erp-orders"]
        assert (o["kind"], o["name"], o["system"], o["runner"]) == ("pipeline", "erp_orders", "SYS-1", "obj-0001")
        assert o["reads"] == ["erp.dbo.Orders"] and o["writes"] == ["bronze.orders"] and o["schedule"] == "daily 02:00"
        assert o["config_entry"] == "sources/config/orders.json:2" and o["enabled"] is True
        assert o["evidence"] == [{"source_id": "src-cfg", "locator": "sources/config/orders.json:2",
                                  "excerpt": "name=erp_orders", "kind": "stated"}]
        assert o["meaning"] == "Flow erp_orders run by nb_ingest: erp.dbo.Orders → bronze.orders"
        assert inv["obj-0001-erp-customers"]["enabled"] is False
        q = inv["obj-0001-by-query"]
        assert q["reads"] == [] and q["source_query"] == "SELECT * FROM erp.dbo.Lines" and "by query" in q["meaning"]
        edges = {(e["from"], e["to"], e["kind"]) for e in rows(run, "dependency_edges")}
        assert ("obj-0001-erp-orders", "obj-0001", "calls") in edges
        assert ("obj-0002", "obj-0001-erp-orders", "triggers") in edges
        assert ("obj-0001-erp-orders", "obj-0100", "writes") in edges              # [bronze].[orders] matches bronze.orders
        assert s["disabled"] == ["obj-0001-erp-customers"] and s["by_query"] == ["obj-0001-by-query"]
        assert s["skipped"] == ["sources/config/_defaults.json:1"]
        assert "erp.dbo.Orders" in s["unmatched"] and "bronze.orders" not in s["unmatched"]
        assert s["files"] == sorted(files)


def test_rerun_adds_one_reports_gone_and_is_byte_identical():
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/f{i}.json": cfg(name=f"f{i}", src=f"s.t{i}", tgt=f"b.t{i}") for i in range(3)}
        root, run = project(d, files, fw())
        old = {"id": "obj-0001-old", "kind": "pipeline", "name": "old", "runner": "obj-0001", "status": "reviewed"}
        (run.parents[1] / "registers").mkdir()
        (run.parents[1] / "registers" / "inventory.jsonl").write_text(json.dumps(old) + "\n")
        x.expand(run, "obj-0001")
        first = (run / "inventory.jsonl").read_bytes(), (run / "dependency_edges.jsonl").read_bytes()
        assert x.expand(run, "obj-0001")["new"] == 0
        assert ((run / "inventory.jsonl").read_bytes(), (run / "dependency_edges.jsonl").read_bytes()) == first
        (root / "sources/config/f3.json").write_text(cfg(name="f3", src="s.t3", tgt="b.t3"))
        (root / "sources/config/f0.json").unlink()
        s = x.expand(run, "obj-0001")
        assert (s["flows"], s["new"], s["replaced"]) == (3, 1, 2) and s["gone"] == ["obj-0001-f0", "obj-0001-old"]
        ids = [r["id"] for r in rows(run, "inventory")]
        assert len(ids) == len(set(ids)) and "obj-0001-f3" in ids and "obj-0001-f0" in ids     # gone is reported, not deleted


CSV = ("FlowName,Src,Sink,Frequency,IsEnabled,SourceConnection\n"
       "h1,s.h1,b.h1,H,1,Server=x;Password=Synthetic1\n"
       "d1,s.d1,b.d1,D,0,Server=x;Password=Synthetic1\n"
       "h2,s.h2,b.h2,H,1,Server=x;Password=Synthetic1\n")


def routed(freq, dispatcher, schedule):
    return fw(entries={"format": "csv", "path": "sources/ctl.csv", "where": [{"field": "Frequency", "equals": freq}]},
              key="FlowName", fields={"source": "Src", "target": "Sink", "enabled": "IsEnabled"},
              dispatcher=dispatcher, schedule=schedule)


def test_descriptions_route_entries_and_refuse_overlap():
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/ctl.csv": CSV}, [routed("H", "obj-0010", "hourly"), routed("D", "obj-0011", "daily 03:00")],
                            runner_extra={"kind": "pipeline", "name": "PL_Copy_One"})
        x.expand(run, "obj-0001")
        inv = {r["id"]: r for r in rows(run, "inventory") if r.get("runner")}
        assert sorted(inv) == ["obj-0001-d1", "obj-0001-h1", "obj-0001-h2"]
        assert inv["obj-0001-h1"]["schedule"] == "hourly" and inv["obj-0001-d1"]["schedule"] == "daily 03:00"
        assert inv["obj-0001-d1"]["enabled"] is False and inv["obj-0001-h1"]["config_entry"] == "sources/ctl.csv:2"
        assert "Password" not in (run / "inventory.jsonl").read_text() + (run / "dependency_edges.jsonl").read_text()
        trig = {(e["from"], e["to"]) for e in rows(run, "dependency_edges") if e["kind"] == "triggers"}
        assert {("obj-0010", "obj-0001-h1"), ("obj-0011", "obj-0001-d1")} <= trig and ("obj-0010", "obj-0001-d1") not in trig
    with tempfile.TemporaryDirectory() as d:                     # two descriptions covering one entry would count it twice
        unrouted = fw(entries={"format": "csv", "path": "sources/ctl.csv"}, key="FlowName", fields={"source": "Src", "target": "Sink"})
        root, run = project(d, {"sources/ctl.csv": CSV}, [routed("H", None, "h"), unrouted])
        assert_refused(lambda: x.expand(run, "obj-0001"), "two descriptions")


def test_expand_refuses_and_writes_nothing():
    one = {"sources/config/a.json": cfg(name="a", src="s", tgt="t")}
    for files, framework, msg in (
            ({**one, "sources/config/b.json": cfg(name="A!", src="s", tgt="t")}, fw(), "same id"),
            (one, fw(fields={"source": "ConnectionString", "target": "tgt"}), "credential"),
            (one, fw(fields={"source": "src"}), "target"),
            (one, None, "no framework")):
        with tempfile.TemporaryDirectory() as d:
            root, run = project(d, files, framework)
            before = (run / "inventory.jsonl").read_bytes()
            assert_refused(lambda: x.expand(run, "obj-0001"), msg)
            assert (run / "inventory.jsonl").read_bytes() == before and not (run / "dependency_edges.jsonl").exists()
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, one, fw())
        assert_refused(lambda: x.expand(run, "obj-0404"), "obj-0404")


def test_incomplete_entry_is_written_and_listed():
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/config/a.json": cfg(name="a", tgt="b.a"), "sources/config/b.json": cfg(name="b", src="s.b")}, fw())
        s = x.expand(run, "obj-0001")
        assert s["flows"] == 2 and s["incomplete"] == ["obj-0001-a", "obj-0001-b"]


def test_numeric_key():
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/ctl.csv": "FlowId,Src,Sink\n17,s.a,b.a\n"},
                            fw(entries={"format": "csv", "path": "sources/ctl.csv"}, key="FlowId", fields={"source": "Src", "target": "Sink"}))
        x.expand(run, "obj-0001")
        flow = next(r for r in rows(run, "inventory") if r.get("runner"))
        assert (flow["id"], flow["name"]) == ("obj-0001-17", "17")


def test_cli_prints_the_summary():
    import subprocess, sys
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/config/a.json": cfg(name="a", src="s", tgt="t")}, fw())
        out = subprocess.run([sys.executable, str(Path(x.__file__)), "expand", str(run), "obj-0001"],
                             check=True, capture_output=True, text=True).stdout
        assert json.loads(out)["flows"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail.**
Run: `uv run -q --no-project --with pytest python -m pytest -q test_expand_flows.py`
Expected: the 7 new tests FAIL with `AttributeError: module 'expand_flows' has no attribute 'expand'`, and the 4 tests from Task 1 pass.

- [ ] **Step 3: Implement `expand`, `inventory_of` and `main` in `expand_flows.py`.** Rules beyond the interfaces:
  - **Finding the description:**
    - Look the runner up through `inventory_of`. If it is missing, refuse with "runner <id> is not in the run's or the registers' inventory".
    - If it has no `framework`, refuse with "<id> has no framework description".
    - A `dict` description becomes a one-item list.
  - **Checking a description before reading anything:**
    - `fields.target` is present, and so is `fields.source` or `fields.source_query`. Otherwise refuse, naming the missing field.
    - `key` and `source_id` are present.
    - `evidence` holds at least one entry with a locator.
    - Split every mapped path and template placeholder on `.`. If any segment matches `write_records.CREDENTIAL_KEY`, refuse with "… names a credential …".
  - **Collecting entries:**
    - For each description, keep the entries `matches` its `where`.
    - If one `(path, line)` is covered by two descriptions, refuse with "… covered by two descriptions — their `where` overlap".
    - An entry with no key value is skipped and listed as `path:line`.
  - **Ids:** `f"{runner_id}-{slug(name)}"`. If two entries give the same id, refuse with "<loc1> and <loc2> give the same id <id>".
  - **Values:**
    - `enabled` comes from `truthy(resolve(..., raw=True))`.
    - `schedule` is the entry's value, else the description's.
    - The excerpt is `f"{key}={name}"`, cut to 120 characters.
    - `meaning` is `f"Flow {name} run by {runner name}: {source or 'by query'} → {target or '?'}"`, cut to 160.
  - **Incomplete entries:** an entry with no target, or with neither a source nor a source query, is incomplete.
  - **Summary lists:**
    - `disabled`: flows with `enabled is False`.
    - `by_query`: flows with a `source_query` and no `source`.
  - **Name matching:**
    - Only inventory records whose kind is in `write_records.KINDS["data"]` are candidates.
    - Normalise both names: lower-case, with `[`, `]`, `` ` `` and `"` removed.
    - A match is an equal name, or one name ending with `"." + the other`.
    - Exactly one match gives an edge. No match puts the name in `unmatched`. Several matches put it in `ambiguous`.
  - **Gone:** a flow in `inventory_of(...)` with `runner == runner_id` and `kind == "pipeline"` whose id was not produced this run.
  - **Writing:** check every record with `write_records.problems(...)` first. If anything is refused, raise `SystemExit` with all the refusals and write nothing. Otherwise `write_records.write(run_dir, "inventory", …)` and then `"dependency_edges"`.
  - **Determinism:** build each dict in the fixed key order, keep entries sorted, and add no timestamps.

- [ ] **Step 4: Run the tests to verify they pass.**
Run: the Step 2 command.
Expected: `11 passed`.

- [ ] **Step 5: Commit.**
```bash
git add databricks-discovery/skills/legacy-etl-archaeology/scripts/expand_flows.py databricks-discovery/skills/legacy-etl-archaeology/scripts/test_expand_flows.py
git commit -m "databricks-discovery: expand_flows.py expand — one pipeline record per configured flow (VEL-1723)"
```

---

### Task 3: `decide` — a framework's rationalization in one go

**Files:**
- Modify: `…/legacy-etl-archaeology/scripts/expand_flows.py`
- Test: `…/legacy-etl-archaeology/scripts/test_expand_flows.py` (append)

**Interfaces:**
- Consumes:
  - `inventory_of(run_dir, registers)`;
  - the flow record keys from Task 2;
  - `write_records.DISPOSITIONS["workloads"]` = `("convert", "rewrite", "retire", "keep")`.
- Produces:
  - `decide(run_dir: Path, runner_id: str, default: str, exceptions: dict, registers: Optional[Path] = None) -> dict`:
    - Writes the `rationalization` register.
    - Returns `{"runner": <disposition>, "dispatchers": {id: disposition}, "flows": int, "by_disposition": {word: count}}`.
  - The CLI subcommand `decide <run-dir> <runner-id> <disposition> [--except ID=DISP ...] [--registers G]`.
  - A flow's rationalization row has these keys:
    - `object_id`, `kind`, `name`, `runner`, `disposition`, `wave` (None), `target_component`, `criteria` ({}), `evidence` (the flow's), `blocking` ([]), `notes`.

- [ ] **Step 1: Write the failing test.**

```python
def test_decide_writes_one_row_per_flow_and_the_runner_follows():
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}", active=a) for n, a in (("a", 1), ("b", 1), ("c", 0))}
        root, run = project(d, files, fw(fields={"source": "src", "target": "tgt", "enabled": "active"}, dispatcher="obj-0002"),
                            inventory=[obj("obj-0002", "pipeline", "PL_All")])
        x.expand(run, "obj-0001")
        s = x.decide(run, "obj-0001", "convert", {"obj-0001-b": "rewrite"})
        rat = {r["object_id"]: r for r in rows(run, "rationalization")}
        assert {k: r["disposition"] for k, r in rat.items()} == {
            "obj-0001-a": "convert", "obj-0001-b": "rewrite", "obj-0001-c": "retire", "obj-0001": "convert", "obj-0002": "convert"}
        assert rat["obj-0001-a"]["target_component"] == "generic Databricks runner — entry a"
        assert rat["obj-0001-b"]["target_component"] == "<catalog>.bronze.b (native ingestion)"
        assert (rat["obj-0001-a"]["runner"], rat["obj-0001-a"]["kind"]) == ("obj-0001", "pipeline")
        assert "owner confirms" in rat["obj-0001-c"]["notes"]
        assert s["by_disposition"] == {"convert": 1, "rewrite": 1, "retire": 1} and s["flows"] == 3
        x.decide(run, "obj-0001", "rewrite", {})
        rat = {r["object_id"]: r["disposition"] for r in rows(run, "rationalization")}
        assert (rat["obj-0001"], rat["obj-0002"]) == ("retire", "retire")              # no flow left on the runner
        x.decide(run, "obj-0001", "keep", {"obj-0001-c": "keep"})                      # an explicit exception beats the disabled rule
        rat = {r["object_id"]: r["disposition"] for r in rows(run, "rationalization")}
        assert (rat["obj-0001-c"], rat["obj-0001"]) == ("keep", "keep")
        assert_refused(lambda: x.decide(run, "obj-0001", "migrate", {}), "migrate")
        assert_refused(lambda: x.decide(run, "obj-0001", "convert", {"obj-9999": "keep"}), "obj-9999")
```

- [ ] **Step 2: Run the test to verify it fails.**
Run: `uv run -q --no-project --with pytest python -m pytest -q test_expand_flows.py -k decide`
Expected: FAIL with `AttributeError: … no attribute 'decide'`.

- [ ] **Step 3: Implement `decide` and its CLI subcommand.**
  - **Flows:** the `inventory_of` records with this `runner` and `kind == "pipeline"`, sorted by id.
  - **Refusals:**
    - a default or exception value outside the workload words, naming it and the allowed words;
    - an exception id that is not one of the runner's flows.
  - **Each flow's disposition:** an explicit exception first. Otherwise `retire` when `enabled is False`, with the note "disabled in the configuration (enabled = false); the owner confirms retirement". Otherwise the default.
  - **target_component:**
    - `convert`: `"generic Databricks runner — entry <name>"`;
    - `rewrite`: `"<catalog>.bronze.<last dot segment of writes[0], else <table>> (native ingestion)"`;
    - `keep`: `"stays where it runs (<runner name>)"`;
    - `retire`: `None`.
  - **Runner, and every distinct non-null `dispatcher` in its descriptions:**
    - `convert` if any flow is convert, `keep` if any is keep, else `retire`.
    - `kind` and `name` come from their inventory records.
    - The note is `"follows its <n> flows"`.
    - target_component is `"generic Databricks runner"` / `"stays where it runs"` / `None`.
  - **Writing:** one `write_records.write(run_dir, "rationalization", rows)`.

- [ ] **Step 4: Run the tests to verify they pass.**
Run: `uv run -q --no-project --with pytest python -m pytest -q test_expand_flows.py`
Expected: `12 passed`.

- [ ] **Step 5: Commit.**
```bash
git add databricks-discovery/skills/legacy-etl-archaeology/scripts/expand_flows.py databricks-discovery/skills/legacy-etl-archaeology/scripts/test_expand_flows.py
git commit -m "databricks-discovery: expand_flows.py decide — a framework's dispositions per flow (VEL-1723)"
```

---

### Task 4: Deliverables — every layer's dispositions, a framework as one row

**Files:**
- Modify: `…/assessment-synthesis/scripts/build_deliverables.py`:
  - `DISPOSITIONS` (line 33);
  - Summary (around line 212–219);
  - the Inventory sheet (around line 281);
  - §4 (around line 605);
  - §9 (around line 680–697);
  - §10 (around line 711–715).
- Modify: `…/assessment-synthesis/references/report-template.md` (rows 4, 9, 10).
- Test: `…/assessment-synthesis/scripts/test_build.py` (append a module-level block before the final `print`).

**Interfaces:**
- Consumes:
  - the flow keys `runner`, `enabled`, `schedule` on inventory records;
  - `runner` on rationalization rows (Task 3).
- Produces (in `build_deliverables.py`):
  - `LAYER_DISPOSITIONS: dict[str, list[str]]`, equal to `write_records.DISPOSITIONS` with lists in place of tuples.
  - `ALL_DISPOSITIONS: list[str]` — `migrate, modernize, retire, defer, convert, rewrite, keep, repoint, replace`.
  - `framework_groups(records: list) -> tuple[list, dict]` — returns the records without a `runner` and the rest grouped as `{runner_id: [flows]}`. Insertion order is kept.

- [ ] **Step 1: Write the failing test block.** Append it to `test_build.py`, before `print("test_build: ok")`.

```python
# ---------- frameworks (VEL-1723): workload dispositions are decisions; a framework is one row in the report ----------
sys.path.insert(0, str(HERE.parents[1] / "discovery-intake" / "scripts"))
import build_deliverables as bd  # noqa: E402
import theme  # noqa: E402
import write_records  # noqa: E402
assert {k: list(v) for k, v in write_records.DISPOSITIONS.items()} == bd.LAYER_DISPOSITIONS   # keep the two in step


def framework_project(tmp):
    root = tmp / "assessment" / "flows"
    reg = root / "registers"
    flows = range(45)
    write(reg / "inventory.jsonl",
          [{"id": "obj-1", "kind": "notebook", "name": "nb_ingest", "evidence": EV, "status": "reviewed"},
           {"id": "obj-2", "kind": "procedure", "name": "sp_load", "evidence": EV, "status": "reviewed"}]
          + [{"id": f"obj-1-f{i}", "kind": "pipeline", "name": f"f{i}", "runner": "obj-1", "schedule": "daily",
              "enabled": i != 0, "evidence": EV, "status": "reviewed"} for i in flows])
    write(reg / "rationalization.jsonl",
          [{"object_id": "obj-1", "kind": "notebook", "name": "nb_ingest", "disposition": "convert",
            "target_component": "generic Databricks runner", "status": "reviewed"},
           {"object_id": "obj-2", "kind": "procedure", "name": "sp_load", "disposition": "rewrite",
            "target_component": "<catalog>.silver.x", "status": "reviewed"}]
          + [{"object_id": f"obj-1-f{i}", "kind": "pipeline", "name": f"f{i}", "runner": "obj-1",
              "disposition": "retire" if i == 0 else "rewrite" if i == 1 else "convert",
              "target_component": None if i == 0 else f"generic Databricks runner — entry f{i}", "status": "reviewed"} for i in flows])
    (root / "intake.md").write_text("# Intake\n")
    return root


with tempfile.TemporaryDirectory() as d:
    root = framework_project(Path(d))
    md = build(root)
    s4 = md.split("## 4. Workload catalogue")[1].split("\n## 5.")[0]
    assert "47 workloads (45 of them flows of 1 framework)" in s4, s4[:300]
    assert "nb_ingest — 45 flows (1 disabled)" in s4 and "| f7 |" not in s4, s4
    s9 = md.split("## 9. Migration complexity & scope")[1].split("\n## 10.")[0]
    assert "**47 of 47 objects decided (100%)" in s9, s9[:300]                       # convert / rewrite / retire are decisions
    assert "| Kind | retire | convert | rewrite | undecided |" in s9 and "| pipeline | 1 | 43 | 1 | 0 |" in s9, s9
    assert "nb_ingest — 45 flows" in s9 and "retire 1 · convert 43 · rewrite 1" in s9 and "| f7 |" not in s9, s9
    s10 = md.split("## 10. Target architecture & component mapping")[1].split("\n## 11.")[0]
    assert "nb_ingest — 45 flows" in s10 and "entry f7" not in s10 and "<catalog>.silver.x" in s10, s10
    from openpyxl import load_workbook
    wb = load_workbook(root.parent / "out-final" / "discovery-flows.xlsx")
    hdr = [c.value for c in next(wb["Inventory"].iter_rows(max_row=1))]
    assert hdr[2:4] == [theme.header_label("name"), theme.header_label("runner")], hdr
    assert sum(1 for r in wb["Rationalization"].iter_rows(min_row=2) if r[0].value) == 47        # one row per flow
    summary = {r[0].value: r[1].value for r in wb["Summary"].iter_rows() if r[0].value}
    assert (summary.get("convert"), summary.get("rewrite"), summary.get("undecided")) == (44, 2, 0), summary
```

- [ ] **Step 2: Run it to verify it fails.**
Run: `cd databricks-discovery/skills/assessment-synthesis/scripts && uv run -q --no-project --with openpyxl python test_build.py`
Expected: `AttributeError: module 'build_deliverables' has no attribute 'LAYER_DISPOSITIONS'`.

- [ ] **Step 3: Implement the changes in `build_deliverables.py`.**
  - **Constants:**
    - Replace `DISPOSITIONS` with `LAYER_DISPOSITIONS`, `ALL_DISPOSITIONS` and a comment "keep in step with discovery-intake/scripts/write_records.py DISPOSITIONS (test_build checks it)".
    - Add `framework_groups`.
  - **Summary sheet:** one row per word of `ALL_DISPOSITIONS`, then `undecided`.
  - **§9 headline:**
    - Decided means a disposition in `ALL_DISPOSITIONS` other than `defer`.
    - Add this sentence after the existing scope sentence: "Workloads: convert and rewrite in, keep stays where it runs, retire out."
  - **§9 kind × disposition table:** its columns are the `ALL_DISPOSITIONS` words used by at least one row, then `undecided`.
  - **§9 per-object table:**
    - Each group of `framework_groups(rat)` becomes one row at its first flow's place.
    - The row reads `[f"{runner name} — {n} flows", "pipeline (flows)", " · ".join(f"{word} {count}" in ALL_DISPOSITIONS order, then undecided), None, the flows' waves joined unique or None, the flows' blocking joined unique]`.
    - The runner's name comes from the inventory record with that id, else the runner's rationalization row, else the id.
  - **§10 mapping:**
    - The mapped rows outside any group stay as they are.
    - Each group with any mapped flow becomes one row: `[f"{runner name} — {n} flows", same disposition string, "per flow — workbook tab Rationalization"]`.
  - **§4 workload catalogue:**
    - The count line is `f"{len(wl)} workloads ({nflows} of them flows of {nfw} framework{'s' if nfw != 1 else ''}) · …"` when there are flows. Otherwise it stays unchanged.
    - Each group becomes one row: `[f"{runner name} — {n} flows ({k} disabled)" (omit the parenthesis when k == 0), "pipeline (flows)", the unique schedules joined with ", " (or "various" past 3), None, the runner's owner or "NOT SET", "workbook tab Inventory"]`.
  - **Inventory sheet:** a `runner` column right after `name`.
  - **`report-template.md`:** rows 4, 9 and 10 each get "a framework's flows are one row (its runner, the count by disposition); the workbook keeps one row per flow".

- [ ] **Step 4: Run the tests to verify they pass.**
Run: `uv run -q --no-project --with openpyxl python test_build.py`
Expected: `test_build: ok`, which covers the earlier blocks unchanged.

- [ ] **Step 5: Commit.**
```bash
git add databricks-discovery/skills/assessment-synthesis/scripts/build_deliverables.py databricks-discovery/skills/assessment-synthesis/scripts/test_build.py databricks-discovery/skills/assessment-synthesis/references/report-template.md
git commit -m "databricks-discovery: workload dispositions count as decisions; a framework is one row in the report (VEL-1723)"
```

---

### Task 5: Fixture `framework-config-files` and eval 6

**Files:**
- Create under `databricks-discovery/evals/fixtures/framework-config-files/`:
  - `README.md` — the purpose and the test prompt, as `minhphat-migration/README.md` has them;
  - `TRAPS.md` — for graders;
  - `sources/` — a Synapse Git export:
    - `pipeline/PL_Ingest_All.json`;
    - `pipeline/PL_Refresh_Dim_Date.json`;
    - `notebook/nb_ingest_generic.json`;
    - `trigger/TR_Ingest_Daily.json`;
    - `config/ingest/*.json`.
- Modify: `databricks-discovery/evals/evals.json` (append id 6).
- Test: `…/legacy-etl-archaeology/scripts/test_expand_flows.py` (append a fixture check).

**Interfaces:**
- Consumes: `expand(run_dir, runner_id)` (Task 2).
- Produces: the facts below, which eval 6's assertions rely on.

**Facts the fixture must hold** (the rest of its content is the builder's call; use synthetic names only):
- **`PL_Ingest_All`:** a GetMetadata activity on `config/ingest/` → ForEach over `childItems` → a SynapseNotebook activity calling `nb_ingest_generic` with parameter `config_path = @item().name`.
- **`TR_Ingest_Daily`:** a ScheduleTrigger, daily 02:00 UTC, referencing `PL_Ingest_All`.
- **`nb_ingest_generic`:** the notebook's cell source reads `cfg["flow_name"]`, `cfg["source"].get("table")`, `cfg["source"].get("query")`, `cfg["sink"]["schema"]`, `cfg["sink"]["table"]`, `cfg.get("load_type", "full")`, `cfg.get("active", True)`. It never reads `target_table`.
- **`config/ingest/`:**
  - 7 flow files, each with `flow_name`, `source`, `sink` and a legacy `target_table` whose value starts with `stg_` and is never read;
  - one flow with `"active": false`;
  - one flow with `source.query` and no `source.table`;
  - `_defaults.json` with no `flow_name`.
- **`PL_Refresh_Dim_Date`:** an ordinary pipeline with one SqlPoolStoredProcedure activity and no loop.

- [ ] **Step 1: Write the failing fixture check.**

```python
FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures"


def fixture_project(tmp, name, framework, runner_extra=None, inventory=()):
    root = Path(tmp)
    import shutil
    shutil.copytree(FIXTURES / name / "sources", root / "sources")
    run = root / "assessment" / "proj" / "runs" / "2026-11-16_run-01"
    runner = {"id": "obj-0001", "kind": "notebook", "name": "nb_ingest_generic", "system": "SYS-1", "evidence": EV,
              "meaning": "the generic ingestion notebook", "framework": framework, **(runner_extra or {})}
    w.write(run, "inventory", [runner, *inventory])
    return root, run


def test_fixture_config_files():
    with tempfile.TemporaryDirectory() as d:
        root, run = fixture_project(d, "framework-config-files", fw(
            entries={"format": "json_files", "path": "sources/config/ingest/*.json"}, key="flow_name",
            fields={"source": "source.table", "source_query": "source.query", "target": "{sink.schema}.{sink.table}",
                    "load": "load_type", "enabled": "active"},
            schedule="daily 02:00 UTC (trigger TR_Ingest_Daily)", dispatcher="obj-0002"),
            inventory=[obj("obj-0002", "pipeline", "PL_Ingest_All")])
        s = x.expand(run, "obj-0001")
        assert s["flows"] == 7 and len(s["disabled"]) == 1 and len(s["by_query"]) == 1, s
        assert s["skipped"] == ["sources/config/ingest/_defaults.json:1"], s
        assert s["incomplete"] == [], s
        writes = [t for r in rows(run, "inventory") if r.get("runner") for t in r["writes"]]
        assert len(writes) == 7 and not any(t.startswith("stg_") for t in writes), writes
```

- [ ] **Step 2: Run it to verify it fails.**
Run: `uv run -q --no-project --with pytest python -m pytest -q test_expand_flows.py -k fixture_config`
Expected: FAIL with `FileNotFoundError` on `evals/fixtures/framework-config-files/sources`.

- [ ] **Step 3: Create the fixture** with the facts above, plus its `README.md` and `TRAPS.md`. TRAPS.md lists:
  - the legacy `target_table`;
  - `_defaults.json`;
  - the inactive and the query entries;
  - `PL_Refresh_Dim_Date` is not a framework;
  - the expected counts (7 flows, 1 disabled, 1 by query, 1 skipped).

- [ ] **Step 4: Run it to verify it passes.**
Run: the Step 2 command.
Expected: `1 passed`.

- [ ] **Step 5: Append eval 6 to `evals.json`.**
  - `id`: 6.
  - `name`: `"framework-config-files"`.
  - `files`: `["evals/fixtures/framework-config-files/sources/"]`.
  - `prompt`: "Lumen Freight's ingestion runs in an Azure Synapse workspace; the Git export of its pipelines, notebooks, triggers and the ingestion config folder is in sources/. Run the archaeology on it before we plan the move to Databricks: inventory, dependencies and a rationalization draft."
  - `expected_output`: one sentence.
  - `assertions` (verbatim):
    1. "Recognises a metadata-driven framework: nb_ingest_generic is the runner, the JSON files in sources/config/ingest/ its entries, PL_Ingest_All (GetMetadata → ForEach → notebook) the dispatcher and TR_Ingest_Daily its schedule"
    2. "Writes `framework` on the runner's inventory record with the mapping taken from the notebook's code — target from sink.schema + sink.table, source from source.table, source_query from source.query, enabled from active — with a locator into the notebook; does NOT map the legacy target_table key the notebook never reads"
    3. "Runs expand_flows.py expand and does not write the flow records by hand: 7 pipeline records, one per entry; _defaults.json skipped; the inactive entry recorded with enabled false; the query entry with source_query"
    4. "Each flow has a calls edge to the runner and a triggers edge from PL_Ingest_All"
    5. "Does NOT expand PL_Refresh_Dim_Date: it stays one ordinary pipeline record calling a procedure"
    6. "Rationalization through expand_flows.py decide with default convert (the runner is a PySpark notebook); the inactive flow retire with the owner to confirm; the runner and the dispatcher convert"
    7. "review.md carries the script's summary — the disabled and query-read flows and the names with no inventory match — and manifest.json lists the config files read"
    8. "The report's workload catalogue shows the framework as one row with its flow count"

- [ ] **Step 6: Check `evals.json` parses.**
Run: `python3 -c "import json; print(len(json.load(open('databricks-discovery/evals/evals.json'))['evals']))"`
Expected: `7`.

- [ ] **Step 7: Commit.**
```bash
git add databricks-discovery/evals/fixtures/framework-config-files databricks-discovery/evals/evals.json databricks-discovery/skills/legacy-etl-archaeology/scripts/test_expand_flows.py
git commit -m "databricks-discovery: fixture and eval 6 — a notebook framework over JSON configs (VEL-1723)"
```

---

### Task 6: Fixture `framework-control-table` and eval 7

**Files:**
- Create under `databricks-discovery/evals/fixtures/framework-control-table/`:
  - `README.md`;
  - `TRAPS.md`;
  - `sources/` — a Synapse Git export plus an export:
    - `pipeline/PL_Ingest_Hourly.json`;
    - `pipeline/PL_Ingest_Daily.json`;
    - `pipeline/PL_Copy_One.json`;
    - `trigger/TR_Hourly.json`;
    - `trigger/TR_Daily_0300.json`;
    - `sqlscript/ctl.IngestControl.sql` (the DDL);
    - `exports/ctl_IngestControl.csv`.
- Modify: `databricks-discovery/evals/evals.json` (append id 7).
- Test: `test_expand_flows.py` (append).

**Interfaces:**
- Consumes: `expand`, `fixture_project` (Task 5).
- Produces: the facts below, which eval 7's assertions rely on.

**Facts the fixture must hold:**
- **`PL_Ingest_Hourly`:** a Lookup with `SELECT * FROM ctl.IngestControl WHERE Frequency = 'H' AND IsEnabled = 1` → ForEach → ExecutePipeline `PL_Copy_One`, passing `@item().SourceQuery`, `@item().SinkSchema` and `@item().SinkTable`. `TR_Hourly` triggers it hourly at :15.
- **`PL_Ingest_Daily`:** the same with `'D'`. `TR_Daily_0300` triggers it daily at 03:00 UTC.
- **`PL_Copy_One`:** the parameterised Copy (source query → ADLS sink `bronze/<SinkSchema>/<SinkTable>`).
- **CSV columns:** `FlowId, FlowName, SourceSystem, SourceConnection, SourceQuery, SinkSchema, SinkTable, TargetTable_Old, Frequency, IsEnabled`.
- **CSV rows:** 10 of them.
  - 6 have `H`, one of them with `IsEnabled = 0`.
  - 4 have `D`, one of them with `IsEnabled = 0`.
  - `crm_contacts_delta` (H) and `crm_contacts_full` (D) both have `SinkSchema.SinkTable = bronze.crm_contacts`.
  - `SourceConnection` holds a fake connection string containing `Password=Synthetic`.

- [ ] **Step 1: Write the failing fixture check.**

```python
def test_fixture_control_table():
    one = lambda f, disp, sched: fw(
        entries={"format": "csv", "path": "sources/exports/ctl_IngestControl.csv", "where": [{"field": "Frequency", "equals": f}]},
        key="FlowName", fields={"source_query": "SourceQuery", "target": "{SinkSchema}.{SinkTable}", "enabled": "IsEnabled"},
        schedule=sched, dispatcher=disp, source_id="src-ctl-01")
    with tempfile.TemporaryDirectory() as d:
        root, run = fixture_project(d, "framework-control-table",
                                    [one("H", "obj-0010", "hourly at :15 (trigger TR_Hourly)"),
                                     one("D", "obj-0011", "daily 03:00 UTC (trigger TR_Daily_0300)")],
                                    runner_extra={"kind": "pipeline", "name": "PL_Copy_One"})
        s = x.expand(run, "obj-0001")
        assert s["flows"] == 10 and len(s["disabled"]) == 2 and len(s["by_query"]) == 10, s
        flows = [r for r in rows(run, "inventory") if r.get("runner")]
        assert sum(1 for r in flows if r["writes"] == ["bronze.crm_contacts"]) == 2
        text = "".join((run / f).read_text() for f in ("inventory.jsonl", "dependency_edges.jsonl"))
        assert "Password" not in text and "TargetTable_Old" not in text
```

- [ ] **Step 2: Run it to verify it fails.**
Run: `uv run -q --no-project --with pytest python -m pytest -q test_expand_flows.py -k fixture_control`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Create the fixture**, plus its `README.md` and `TRAPS.md`. TRAPS.md lists:
  - `IsEnabled` is the on/off switch, not routing;
  - `Frequency` is routing between two dispatchers;
  - `TargetTable_Old` is never read;
  - two flows share a target, which should produce a finding;
  - `SourceConnection` must never reach a register;
  - the expected counts (10 flows, 2 disabled, 6 hourly, 4 daily).

- [ ] **Step 4: Run it to verify it passes.**
Run: the Step 2 command.
Expected: `1 passed`.

- [ ] **Step 5: Append eval 7 to `evals.json`.**
  - `id`: 7.
  - `name`: `"framework-control-table"`.
  - `files`: `["evals/fixtures/framework-control-table/sources/"]`.
  - `prompt`: "Lumen Freight also lands ERP and CRM tables with Synapse pipelines driven by a control table; sources/ holds the pipeline and trigger JSON, the table's DDL and an export of its rows. Run the archaeology and draft the rationalization."
  - `assertions` (verbatim):
    1. "Recognises PL_Copy_One (a parameterised Copy) as the runner, fed by two dispatchers, PL_Ingest_Hourly and PL_Ingest_Daily, each a Lookup on ctl.IngestControl → ForEach → ExecutePipeline"
    2. "`framework` on the runner is a list of two descriptions routed by `where` Frequency = 'H' / 'D', each with its dispatcher and its trigger's schedule; IsEnabled is mapped as `enabled`, not used as a `where`"
    3. "10 flow records come from expand_flows.py, 2 with enabled false; target = SinkSchema.SinkTable, not TargetTable_Old; every flow reads by query (source_query)"
    4. "No value of the SourceConnection column appears in any register, review.md or manifest.json"
    5. "Raises a finding that crm_contacts_delta and crm_contacts_full both load bronze.crm_contacts, with both entries' locators"
    6. "Rationalization through expand_flows.py decide with default rewrite (a Copy activity has no runner to move), naming keep in the reason as the option of leaving the copy in place; the disabled flows retire; the runner and both dispatchers retire"
    7. "Every flow count it states comes from the script's summary, not from its own counting"

- [ ] **Step 6: Check `evals.json` parses.**
Run: the Task 5 Step 6 command.
Expected: `8`.

- [ ] **Step 7: Commit.**
```bash
git add databricks-discovery/evals/fixtures/framework-control-table databricks-discovery/evals/evals.json databricks-discovery/skills/legacy-etl-archaeology/scripts/test_expand_flows.py
git commit -m "databricks-discovery: fixture and eval 7 — a Copy framework over a control table, two dispatchers (VEL-1723)"
```

---

### Task 7: Skill text, schema docs and versions

**Files:**
- Create: `…/legacy-etl-archaeology/references/framework-guide.md`.
- Modify:
  - `…/legacy-etl-archaeology/SKILL.md`: a new step **0c** after 0b; `References`; version `0.3.0` → `0.4.0`; the description mentions metadata-driven frameworks.
  - `…/legacy-etl-archaeology/references/dw-artifact-guide.md`: Synapse **Pipelines** bullet.
  - `…/discovery-intake/references/run-layout.md`: the inventory schema comment; version of `discovery-intake/SKILL.md` `0.7.2` → `0.7.3`.
  - `…/assessment-synthesis/SKILL.md`: a new **§1c Frameworks**; `References`; version `0.5.1` → `0.6.0`.
  - `README.md`: the `legacy-etl-archaeology` and `assessment-synthesis` rows.
  - `databricks-discovery/.claude-plugin/plugin.json`: `0.12.1` → `0.13.0`.

**Interfaces:**
- Consumes:
  - the description schema (design §6.2);
  - the CLI from Tasks 2 and 3: `python3 "<directory>/scripts/expand_flows.py" expand <run-dir> <runner-id>` and `… decide <run-dir> <runner-id> <disposition> [--except ID=DISP]`;
  - the summary keys.

Content each file must carry. The wording is the builder's; keep the pack's terse style and its "measured / why" voice.

- [ ] **Step 1: `framework-guide.md`.** Its sections:
  1. **What a framework is:** runner, entries, dispatcher.
  2. **Recognise it.** A table of the common forms:
     - config files + notebook (GetMetadata/ForEach);
     - a control table + Lookup/ForEach + Copy or ExecutePipeline;
     - a config table + a procedure with dynamic SQL or a cursor;
     - a Databricks `for_each` task or an onboarding-file pipeline;
     - a list in code.
     For each form, the table says where the entries are and what the dispatcher is. It also states what is *not* a framework: a loop over dates, partitions or one dataset's files.
  3. **Describe it.** The `framework` schema (design §6.2) and one example:
     - the mapping comes from the keys the runner's code reads, with a locator;
     - `where` is routing and `enabled` is the on/off switch;
     - a list of descriptions is for several dispatchers, or for runners split by type.
  4. **Expand it.** Run the command, never count flows yourself, and handle the summary:
     - `disabled`, `incomplete`, `by_query`, `unmatched` and `ambiguous` go into `review.md`;
     - `gone` means the reviewer rejects those records;
     - `files` go into the manifest;
     - the paths are root-relative.
  5. **Fallback.** For YAML or entries in code, write the records by hand in the same shape and name the framework in `review.md`. If the entries are not in hand, record the runner and the dispatcher, add a source-request line and an open question, and never give a count.
  6. **Secrets.** Never map a credential column; the script refuses it. Control tables often carry connection strings.

- [ ] **Step 2: `legacy-etl-archaeology/SKILL.md`.**
  - Step **0c. Metadata-driven frameworks** is 4–6 lines: recognise → describe on the runner's record → `expand_flows.py expand` → summary into `review.md`. Details are in `references/framework-guide.md`.
  - Add the script's path rule, "run where it is, never copied", as for `write_records.py`.
  - Add the guide to References.
- [ ] **Step 3: `dw-artifact-guide.md`.** One sentence in the Synapse Pipelines bullet: a ForEach that calls one notebook, Copy or ExecutePipeline per `item()` is a framework → `framework-guide.md`.
- [ ] **Step 4: `run-layout.md`.** Under the inventory schema, add:
  - the flow keys `runner`, `config_entry`, `source_query`, `load`, `enabled`, with `reads[]`/`writes[]` being names as configured;
  - `framework` on a runner, pointing to framework-guide §3;
  - on rationalization: "a flow row carries `runner`; a framework's rows are written by `expand_flows.py decide`".
- [ ] **Step 5: `assessment-synthesis/SKILL.md` §1c Frameworks.**
  - Decide per runner with `expand_flows.py decide`, using exceptions only with evidence.
  - Include the default rule (design §8a):
    - PySpark/Python runner → `convert`;
    - Copy or SSIS → `rewrite`, with `keep` named in the reason;
    - procedure → `convert`.
  - A disabled flow → `retire`, with the owner to confirm and an open question.
  - The runner and dispatchers follow their flows.
  - The report shows a framework as one row.
- [ ] **Step 6: README rows, `plugin.json` and the three `version` fields**, as listed under Files.
- [ ] **Step 7: Run the whole suite** (as in the CLAUDE.md loop):
Run: `for d in databricks-discovery/skills/*/scripts; do (cd "$d" && uv run -q --no-project --with pytest --with openpyxl python -m pytest -q); done; (cd databricks-discovery/skills/assessment-synthesis/scripts && uv run -q --no-project --with openpyxl python test_build.py)`
Expected:
- the four scripts folders pass: discovery-intake 10, security-posture 11, legacy-etl-archaeology 14, assessment-synthesis with no pytest functions;
- `test_build: ok`.
- [ ] **Step 8: Check that no client name leaked.**
Run: `grep -rniE "tetra|addepto" databricks-discovery/skills/legacy-etl-archaeology databricks-discovery/evals/fixtures/framework-* databricks-discovery/skills/discovery-intake/references/run-layout.md`
Expected: no output.
- [ ] **Step 9: Commit.**
```bash
git add databricks-discovery/skills/legacy-etl-archaeology/references/framework-guide.md databricks-discovery/skills/legacy-etl-archaeology/SKILL.md databricks-discovery/skills/legacy-etl-archaeology/references/dw-artifact-guide.md databricks-discovery/skills/discovery-intake/references/run-layout.md databricks-discovery/skills/discovery-intake/SKILL.md databricks-discovery/skills/assessment-synthesis/SKILL.md README.md databricks-discovery/.claude-plugin/plugin.json
git commit -m "databricks-discovery 0.13.0: metadata-driven frameworks read as one pipeline per configured flow (VEL-1723)"
```

---

## Not in this plan

- Running evals 6 and 7 against a live model. The pack has no eval runner in the repo; they run the way evals 0–5 do, by hand or through skill-creator, after merge.
- The acceptance run on VEL-1722's estate, once that estate exists.
- Syncing the pack into the desktop (`scripts/sync-velox-skills.mjs`), which is the desktop's own change.
