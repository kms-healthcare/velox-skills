#!/usr/bin/env python3
"""write_manifest.py — write a run's manifest.json: sources hashed, executions checked, counts taken.

    python3 write_manifest.py <run-dir> <fields.json | ->

<fields.json> is a JSON object. `sources` maps a source id to paths (files or folders) relative to
the project root, the folder that holds `discovery/`; every file under them is read and recorded
as path + sha256 + bytes. `executions` is the full list of commands run against the project, each
with `command`, `exit` and `log` (`runs/<run>/logs/…`, relative to discovery/<project>/ as in
run-layout.md; it must exist). Every other key (`skill`, `model`,
`sources_requested_not_available`, `notes`, …) is stored as given.
`run_id`, `project` and `counts` come from the run folder itself.

Merges into an existing manifest: entries a pack script added (posture.py's `external_access`, a
`src-client-posture` source) are kept; a source id given here replaces its own entries only.
Refuses a missing path or an execution without its log, and then writes nothing.

Why a script: measured 2026-10-09, an agent wrote its own build_manifest.py to hash 85 sources —
every run reinvents it, and each invention records a different shape. Stdlib only.
"""
import hashlib
import json
import sys
from pathlib import Path

SKIP = {".git", "node_modules", "__pycache__", ".venv", ".velox"}


def files_under(root, rel):
    p = root / rel
    if p.is_file():
        return [p]
    return sorted(f for f in p.rglob("*") if f.is_file() and not SKIP & set(f.relative_to(root).parts))


def write(run_dir, fields):
    run = Path(run_dir).resolve()
    if run.parent.name != "runs" or run.parents[2].name != "discovery":
        raise SystemExit(f"{run} is not discovery/<project>/runs/<run>")
    root = run.parents[3]
    bad = []
    sources = fields.pop("sources", {}) or {}
    for sid, paths in sources.items():
        bad += [f"{sid}: {p} does not exist" for p in paths if not (root / p).exists()]
    executions = fields.get("executions", [])
    for e in executions:
        missing = [k for k in ("command", "exit", "log") if k not in e]
        if missing:
            bad.append(f"execution {e.get('command')!r}: missing {', '.join(missing)}")
        elif not (run.parents[1] / e["log"]).is_file():
            bad.append(f"execution {e['command']!r}: log {e['log']} does not exist")
    if bad:
        for b in bad:
            print(f"REFUSED {b}", file=sys.stderr)
        raise SystemExit(f"{len(bad)} problem(s); manifest not written")

    read = []
    for sid, paths in sources.items():
        for p in paths:
            for f in files_under(root, p):
                data = f.read_bytes()
                read.append({"source_id": sid, "path": f.relative_to(root).as_posix(),
                             "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})

    path = run / "manifest.json"
    m = json.loads(path.read_text()) if path.exists() else {}
    m.update(fields)
    m["run_id"], m["project"] = run.name, run.parents[1].name
    m["sources_read"] = [s for s in m.get("sources_read", []) if s.get("source_id") not in sources] + read
    m.setdefault("external_access", [])
    m["counts"] = {f.stem: sum(1 for line in f.read_text().splitlines() if line.strip())
                   for f in sorted(run.glob("*.jsonl"))}
    path.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(read), m["counts"]


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit(__doc__)
    text = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text()
    n, counts = write(argv[0], json.loads(text))
    print(f"manifest: {n} sources hashed · counts {counts} · {Path(argv[0]) / 'manifest.json'}")


if __name__ == "__main__":
    main()
