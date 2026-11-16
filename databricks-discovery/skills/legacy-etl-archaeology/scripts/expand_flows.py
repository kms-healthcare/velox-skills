#!/usr/bin/env python3
"""expand_flows.py — a metadata-driven framework's configuration entries as pipeline records.

    python3 expand_flows.py expand <run-dir> <runner-id> [--root R] [--registers G]
    python3 expand_flows.py decide <run-dir> <runner-id> <disposition> [--except ID=DISP ...] [--note TEXT] [--registers G]

A framework is one generic runner (a notebook, a Copy, a procedure) that runs one flow per
configuration entry (a JSON file, an element of a JSON array, a JSONL line, a control-table row),
called by a dispatcher (a ForEach, a `for_each` task, a cursor). The agent describes it once, as
`framework` on the runner's inventory record (references/framework-guide.md); `expand` reads every
entry and writes one `pipeline` record per flow, with its edges, through write_records.py;
`decide` writes the framework's rationalization rows.

Why a script: the flow count comes from a script, never from the model. Read by the model, 21
entries come out right and 200 do not, and a re-run that renames one id duplicates a flow.
Stdlib only.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional

HERE = Path(__file__).resolve().parent
# The pack's one record writer, run where it is (run-layout.md): never copied next to this script.
sys.path.insert(0, str(HERE.parents[1] / "discovery-intake" / "scripts"))
import write_records  # noqa: E402

FORMATS = ("json_files", "json_array", "jsonl", "csv")
TRUE = {"1", "true", "yes", "y", "t", "on"}
FALSE = {"0", "false", "no", "n", "f", "off"}
PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


class Entry(NamedTuple):
    data: dict
    path: str   # relative to the project root, with "/"
    line: int


# ---------- values ----------

def get_path(entry: Any, dotted: str) -> Any:
    """A flat key equal to `dotted` first (a CSV column "Sink.Table"), then the dots walked."""
    if not isinstance(entry, dict) or not dotted:
        return None
    if dotted in entry:
        return entry[dotted]
    cur: Any = entry
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _text(v: Any) -> Optional[str]:
    if v is None or isinstance(v, (dict, list)):
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip()
    return s or None


def resolve(entry: dict, spec: Any, raw: bool = False) -> Any:
    """A dotted path, a template with {dotted.path} placeholders, or a list of those (first non-empty wins)."""
    if spec is None:
        return None
    if isinstance(spec, list):
        for s in spec:
            v = resolve(entry, s, raw)
            if v is not None and v != "":
                return v
        return None
    spec = str(spec)
    if raw:
        return get_path(entry, spec)
    if PLACEHOLDER.search(spec):
        missing = []

        def sub(m: re.Match) -> str:
            v = _text(get_path(entry, m.group(1)))
            if v is None:
                missing.append(m.group(1))
                return ""
            return v

        out = PLACEHOLDER.sub(sub, spec)
        return None if missing else _text(out)
    return _text(get_path(entry, spec))


def truthy(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {1: True, 0: False}.get(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in TRUE:
            return True
        if s in FALSE:
            return False
    return None


def matches(entry: dict, where: Optional[list]) -> bool:
    """Every condition holds: {"field", "equals" | "in" | "not_in"}, compared as text."""
    for c in where or []:
        v = get_path(entry, str(c.get("field") or ""))
        s = None if v is None else str(v)
        if "equals" in c and s != str(c["equals"]):
            return False
        if "in" in c and s not in [str(x) for x in c["in"]]:
            return False
        if "not_in" in c and s in [str(x) for x in c["not_in"]]:
            return False
    return True


def slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(key).lower()).strip("-")


# ---------- reading entries ----------

def _files(root: Path, path: Any) -> list:
    if not path:
        raise SystemExit("entries.path is missing")
    p = str(path).replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
        raise SystemExit(f"{path} is outside the project root — entry paths are relative to the folder that holds assessment/")
    top = root.resolve()
    found = sorted(f for f in root.glob(p) if f.is_file())
    for f in found:
        if not f.resolve().is_relative_to(top):
            raise SystemExit(f"{f} is outside the project root")
    if not found:
        raise SystemExit(f"no entries at {path} — check the path; a framework is never 0 flows")
    return found


def _json(text: str, rel: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{rel} is not valid JSON: {e}")


def _line_of(lines: list, key: str, value: Any, start: int) -> Optional[int]:
    """The 1-based line where the entry's key holds its value, searching from `start` (0-based)."""
    if value is None or isinstance(value, (dict, list)):
        return None
    seg = re.escape(key.split(".")[-1])
    encoded = {json.dumps(value), json.dumps(value, ensure_ascii=False)}
    alt = "|".join(re.escape(e) for e in sorted(encoded))
    pat = re.compile(r'"' + seg + r'"\s*:\s*(?:' + alt + r')' + ("" if isinstance(value, str) else r"(?![\w.])"))
    for i in range(max(start, 0), len(lines)):
        if pat.search(lines[i]):
            return i + 1
    return None


def _pointer(doc: Any, ptr: Optional[str]) -> Any:
    if not ptr:
        return doc
    cur = doc
    for raw in str(ptr).lstrip("/").split("/"):
        tok = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and tok in cur:
            cur = cur[tok]
        elif isinstance(cur, list) and tok.isdigit() and int(tok) < len(cur):
            cur = cur[int(tok)]
        else:
            return None
    return cur


def read_entries(root: Path, spec: dict, key: str) -> list:
    """Every entry the description's `entries` names, sorted by (path, line). `where` is the caller's."""
    fmt = spec.get("format")
    if fmt not in FORMATS:
        raise SystemExit(f"format {fmt!r} is not one of {' / '.join(FORMATS)} — "
                         f"write the flows by hand (framework-guide.md, fallback)")
    out = []
    for f in _files(root, spec.get("path")):
        rel = f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8-sig")   # exports often carry a BOM
        lines = text.splitlines()
        if fmt == "json_files":
            data = _json(text, rel)
            if not isinstance(data, dict):
                raise SystemExit(f"{rel}: one object per file — use json_array for a list")
            out.append(Entry(data, rel, _line_of(lines, key, get_path(data, key), 0) or 1))
        elif fmt == "json_array":
            items = _pointer(_json(text, rel), spec.get("pointer"))
            if not isinstance(items, list):
                raise SystemExit(f"pointer {spec.get('pointer')!r} does not name a list in {rel}")
            prev = 0
            for item in items:
                if not isinstance(item, dict):
                    raise SystemExit(f"{rel}: every entry of the list must be an object")
                line = _line_of(lines, key, get_path(item, key), prev) or 1
                prev = max(prev, line)
                out.append(Entry(item, rel, line))
        elif fmt == "jsonl":
            for i, raw in enumerate(lines, start=1):
                if raw.strip():
                    data = _json(raw, f"{rel}:{i}")
                    if not isinstance(data, dict):
                        raise SystemExit(f"{rel}:{i}: every line must be an object")
                    out.append(Entry(data, rel, i))
        else:
            reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=spec.get("delimiter") or ",")
            reader.fieldnames  # reads the header, so line_num is where it ends
            last = reader.line_num
            for row in reader:
                out.append(Entry({k: v for k, v in row.items() if k is not None}, rel, last + 1))
                last = reader.line_num
    return sorted(out, key=lambda e: (e.path, e.line))


# ---------- the run's records ----------

def _jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def inventory_of(run_dir: Path, registers: Path) -> dict:
    """The run's inventory over the registers' (the run wins), rejected records left out. A record a
    reviewer rejected in the registers stays out even when the run proposes it again: an entry that
    still exists is expanded every run, and its new copy must not undo the reviewer's decision."""
    reg = _jsonl(Path(registers) / "inventory.jsonl")
    rejected = {r.get("id") for r in reg if r.get("status") == "rejected"}
    out = {}
    for r in reg + _jsonl(Path(run_dir) / "inventory.jsonl"):
        if r.get("id"):
            out[r["id"]] = r
    return {k: v for k, v in out.items() if v.get("status") != "rejected" and k not in rejected}


def _locations(run_dir: Any, root: Any, registers: Any) -> tuple:
    run_dir = Path(run_dir).resolve()
    root = Path(root).resolve() if root else run_dir.parents[3]          # <root>/assessment/<project>/runs/<run>
    registers = Path(registers).resolve() if registers else run_dir.parents[1] / "registers"
    return run_dir, root, registers


def _descriptions(runner_id: str, runner: dict) -> list:
    fw = runner.get("framework")
    if not fw:
        raise SystemExit(f"{runner_id} has no framework description — write `framework` on its record first "
                         f"(framework-guide.md)")
    return fw if isinstance(fw, list) else [fw]


def _paths_of(spec: Any) -> list:
    if isinstance(spec, list):
        return [p for s in spec for p in _paths_of(s)]
    if spec is None:
        return []
    found = PLACEHOLDER.findall(str(spec))
    return found or [str(spec)]


def _check(desc: dict) -> list:
    """What is missing or unsafe in one description, before anything is read."""
    out = []
    fields = desc.get("fields") or {}
    if not isinstance(desc.get("entries"), dict):
        out.append("entries is missing")
    if not desc.get("key"):
        out.append("key is missing")
    if not fields.get("target"):
        out.append("fields.target is missing")
    if not (fields.get("source") or fields.get("source_query")):
        out.append("fields.source or fields.source_query is missing")
    if not desc.get("source_id"):
        out.append("source_id is missing")
    if not any(isinstance(e, dict) and e.get("locator") for e in desc.get("evidence") or []):
        out.append("evidence with a locator into the runner's code is missing")
    for name, spec in [("key", desc.get("key"))] + list(fields.items()):
        for path in _paths_of(spec):
            if any(write_records.CREDENTIAL_KEY.match(seg.strip()) for seg in path.split(".")):
                out.append(f"{name} ({path}) names a credential — never map a secret into a register")
    return out


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def _norm(name: Any) -> str:
    return re.sub(r'[\[\]`"]', "", str(name or "")).strip().lower()


def _same_name(a: Any, b: Any) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def _refuse_if_bad(register: str, records: list) -> None:
    bad = [f"{write_records.key(register, r)}: {'; '.join(p)}" for r in records
           for p in [write_records.problems(register, r)] if p]
    if bad:
        raise SystemExit(f"{len(bad)} {register} records refused; nothing written:\n  " + "\n  ".join(bad))


# ---------- expand ----------

def expand(run_dir: Any, runner_id: str, root: Any = None, registers: Any = None) -> dict:
    """One `pipeline` record per configured flow, with its edges, written into the run. Returns the summary."""
    run_dir, root, registers = _locations(run_dir, root, registers)
    inv = inventory_of(run_dir, registers)
    runner = inv.get(runner_id)
    if runner is None:
        raise SystemExit(f"runner {runner_id} is not in the run's or the registers' inventory")
    descs = _descriptions(runner_id, runner)
    bad = [f"description {i + 1}: {p}" for i, d in enumerate(descs) for p in _check(d)]
    if bad:
        raise SystemExit("framework refused:\n  " + "\n  ".join(bad))

    files, skipped, covered, flows = set(), [], {}, []
    for i, d in enumerate(descs):
        seen = {}
        for e in read_entries(root, d["entries"], str(d["key"])):
            files.add(e.path)
            n = seen[(e.path, e.line)] = seen.get((e.path, e.line), 0) + 1
            if not matches(e.data, d["entries"].get("where")):
                continue
            loc = f"{e.path}:{e.line}"
            if (e.path, e.line, n) in covered:
                raise SystemExit(f"{loc} is covered by two descriptions — their `where` overlap, and the flow would count twice")
            covered[(e.path, e.line, n)] = i
            if resolve(e.data, d["key"]) is None:
                skipped.append(loc)
                continue
            flows.append((e, d))
    if not flows:
        raise SystemExit(f"no entry of {runner_id}'s framework has a key value or matches its `where` — "
                         f"check `key` and `where`; a framework is never 0 flows")

    runner_name = runner.get("name") or runner_id
    data_objs = [r for r in inv.values() if r.get("kind") in write_records.KINDS["data"]]
    ids, records, edges = {}, [], []
    disabled, incomplete, by_query, unmatched, ambiguous = [], [], [], set(), set()
    for e, d in flows:
        f = d.get("fields") or {}
        name = resolve(e.data, d["key"])
        loc = f"{e.path}:{e.line}"
        fid = f"{runner_id}-{slug(name)}"
        if not slug(name):
            raise SystemExit(f"{loc}: the key {name!r} gives an empty id")
        if fid in ids:
            raise SystemExit(f"{ids[fid]} and {loc} give the same id {fid} — keys must differ in more than case or punctuation")
        ids[fid] = loc
        source, query, target = resolve(e.data, f.get("source")), resolve(e.data, f.get("source_query")), resolve(e.data, f.get("target"))
        enabled = truthy(resolve(e.data, f["enabled"], raw=True)) if f.get("enabled") else None
        ev = [{"source_id": d["source_id"], "locator": loc, "excerpt": _cut(f"{d['key']}={name}", 120), "kind": "stated"}]
        shown = source or ("by query" if query else "?")
        records.append({
            "id": fid, "kind": "pipeline", "name": name, "system": runner.get("system"), "runner": runner_id,
            "config_entry": loc, "reads": [source] if source else [], "source_query": query,
            "writes": [target] if target else [], "schedule": resolve(e.data, f.get("schedule")) or _text(d.get("schedule")),
            "load": resolve(e.data, f.get("load")), "enabled": enabled,
            "meaning": _cut(f"Flow {name} run by {runner_name}: {shown} → {target or '?'}", 160), "evidence": ev})
        if enabled is False:
            disabled.append(fid)
        if not target or not (source or query):
            incomplete.append(fid)
        if query and not source:
            by_query.append(fid)
        edges.append({"from": fid, "to": runner_id, "kind": "calls", "evidence": ev,
                      "meaning": _cut(f"Flow {name} runs on {runner_name}", 160)})
        if d.get("dispatcher"):
            disp = d["dispatcher"]
            edges.append({"from": disp, "to": fid, "kind": "triggers", "evidence": d["evidence"],
                          "meaning": _cut(f"{(inv.get(disp) or {}).get('name') or disp} runs flow {name}", 160)})
        for kind, value in (("reads", source), ("writes", target)):
            if not value:
                continue
            hits = [o for o in data_objs if _same_name(o.get("name"), value)]
            if len(hits) == 1:
                edges.append({"from": fid, "to": hits[0]["id"], "kind": kind, "evidence": ev,
                              "meaning": _cut(f"Flow {name} {kind} {hits[0].get('name')}", 160)})
            else:
                (ambiguous if hits else unmatched).add(value)

    _refuse_if_bad("inventory", records)
    _refuse_if_bad("dependency_edges", edges)
    gone = sorted(k for k, r in inv.items() if r.get("runner") == runner_id and r.get("kind") == "pipeline" and k not in ids)
    added, replaced, _ = write_records.write(run_dir, "inventory", records)
    write_records.write(run_dir, "dependency_edges", edges)
    return {"runner": runner_id, "flows": len(records), "new": added, "replaced": replaced,
            "disabled": sorted(disabled), "incomplete": sorted(incomplete), "by_query": sorted(by_query),
            "unmatched": sorted(unmatched), "ambiguous": sorted(ambiguous), "skipped": sorted(skipped),
            "gone": gone, "files": sorted(files)}


# ---------- decide ----------

DISABLED_NOTE = "disabled in the configuration (enabled = false); the owner confirms retirement"


def _target_component(disposition: str, name: str, writes: list, runner_name: str) -> Optional[str]:
    if disposition == "convert":
        return f"generic Databricks runner — entry {name}"
    if disposition == "rewrite":
        table = str(writes[0]).split(".")[-1] if writes else "<table>"
        return f"<catalog>.bronze.{table} (native ingestion)"
    if disposition == "keep":
        return f"stays where it runs ({runner_name})"
    return None


def decide(run_dir: Any, runner_id: str, default: str, exceptions: dict, registers: Any = None,
           note: Optional[str] = None) -> dict:
    """A framework's rationalization rows: every flow (default, exception, disabled → retire), then the runner
    and its dispatchers, which follow their flows. `note` is the reason for the default, kept in the `notes` of
    every flow it decides (a Copy framework's names keep there). Written into the run; returns the summary."""
    run_dir, _, registers = _locations(run_dir, None, registers)
    words = write_records.DISPOSITIONS["workloads"]
    for d in [default, *exceptions.values()]:
        if d not in words:
            raise SystemExit(f"disposition {d!r} is not a workload's: {' / '.join(words)}")
    inv = inventory_of(run_dir, registers)
    runner = inv.get(runner_id)
    if runner is None:
        raise SystemExit(f"runner {runner_id} is not in the run's or the registers' inventory")
    flows = sorted((r for r in inv.values() if r.get("runner") == runner_id and r.get("kind") == "pipeline"),
                   key=lambda r: r["id"])
    unknown = sorted(set(exceptions) - {r["id"] for r in flows})
    if unknown:
        raise SystemExit(f"{', '.join(unknown)} is not a flow of {runner_id}")
    runner_name = runner.get("name") or runner_id
    rows, counts = [], {}
    for f in flows:
        if f["id"] in exceptions:
            disp, note_ = exceptions[f["id"]], None
        elif f.get("enabled") is False:
            disp, note_ = "retire", DISABLED_NOTE
        else:
            disp, note_ = default, note
        counts[disp] = counts.get(disp, 0) + 1
        rows.append({"object_id": f["id"], "kind": "pipeline", "name": f.get("name"), "runner": runner_id,
                     "disposition": disp, "wave": None,
                     "target_component": _target_component(disp, f.get("name"), f.get("writes") or [], runner_name),
                     "criteria": {}, "evidence": f.get("evidence") or [], "blocking": [], "notes": note_})
    follows = "convert" if "convert" in counts else "keep" if "keep" in counts else "retire"
    component = {"convert": "generic Databricks runner", "keep": "stays where it runs"}.get(follows)
    dispatchers = sorted({d.get("dispatcher") for d in _descriptions(runner_id, runner) if d.get("dispatcher")})
    for oid in [runner_id, *dispatchers]:
        rec = inv.get(oid) or {}
        rows.append({"object_id": oid, "kind": rec.get("kind") or "pipeline", "name": rec.get("name") or oid,
                     "disposition": follows, "wave": None, "target_component": component, "criteria": {},
                     "evidence": rec.get("evidence") or [], "blocking": [], "notes": f"follows its {len(flows)} flows"})
    _refuse_if_bad("rationalization", rows)
    write_records.write(run_dir, "rationalization", rows)
    return {"runner": follows, "dispatchers": {d: follows for d in dispatchers}, "flows": len(flows),
            "by_disposition": counts}


# ---------- command line ----------

def main(argv: Optional[list] = None) -> None:
    import argparse
    p = argparse.ArgumentParser(prog="expand_flows.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("expand", help="one pipeline record per configured flow")
    ex.add_argument("run_dir")
    ex.add_argument("runner_id")
    ex.add_argument("--root", help="the project root (default: four levels above the run folder)")
    ex.add_argument("--registers", help="the registers folder (default: <project>/registers)")
    de = sub.add_parser("decide", help="the framework's rationalization rows")
    de.add_argument("run_dir")
    de.add_argument("runner_id")
    de.add_argument("disposition", help="the default for every flow: " + " / ".join(write_records.DISPOSITIONS["workloads"]))
    de.add_argument("--except", dest="exceptions", action="append", default=[], metavar="FLOW_ID=DISPOSITION")
    de.add_argument("--note", help="the reason for the default, kept in the notes of every flow it decides")
    de.add_argument("--registers", help="the registers folder (default: <project>/registers)")
    args = p.parse_args(argv)
    if args.cmd == "expand":
        summary = expand(args.run_dir, args.runner_id, args.root, args.registers)
    else:
        bad = [e for e in args.exceptions if "=" not in e]
        if bad:
            raise SystemExit(f"--except takes FLOW_ID=DISPOSITION, not {bad[0]!r}")
        exceptions = dict(e.split("=", 1) for e in args.exceptions)
        summary = decide(args.run_dir, args.runner_id, args.disposition, exceptions, args.registers, args.note)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
