#!/usr/bin/env python3
"""expand_flows.py — a metadata-driven framework's configuration entries as pipeline records.

    python3 expand_flows.py expand <run-dir> <runner-id> [--root R] [--registers G]
    python3 expand_flows.py decide <run-dir> <runner-id> <disposition> [--except ID=DISP ...] [--registers G]

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
