#!/usr/bin/env python3
"""write_records.py — put records into a run's register, validated, one JSON line each.

    python3 write_records.py <run-dir> <register> <records.json | ->

<records.json> is a JSON array (or JSON Lines) of records. Each is checked against the rules in
references/run-layout.md — an id with the register's prefix, at least one evidence entry with a
locator, excerpts within budget — then upserted by id (rationalization by object_id, edges by from|to|kind) into <run-dir>/<register>.jsonl (a second
write of the same id replaces, it never duplicates). `status` defaults to `extracted`.

Why a script: measured 2026-10-08, an agent wrote 27 KB of records INSIDE a Python file that
printed them as JSONL, because the shell guard refuses `python -c` and the write tool takes one
file at a time. Records that live in a throwaway script are records the reviewer cannot find.
Stdlib only.
"""
import json
import sys
from pathlib import Path

PREFIX = {
    "requirements": ("FR-", "DR-", "SEC-", "NFR-", "SCOPE-", "INT-"),
    "business_rules": ("BR-",),
    "inventory": ("obj-",),
    "findings": ("FND-",),
    "open_questions": ("OQ-",),
    "rationalization": ("obj-",),          # keyed by object_id — one row per inventory object
    "readiness": ("RDY-",),
}
NEEDS_EVIDENCE = {"requirements", "business_rules", "inventory", "findings", "open_questions", "dependency_edges"}
EXCERPT_MAX = 120
TEXT_MAX = {"findings": "detail", "requirements": "statement"}


def key(register, rec):
    if register == "dependency_edges":
        return f"{rec.get('from')}|{rec.get('to')}|{rec.get('kind')}"
    if register == "rationalization":
        return rec.get("object_id")
    return rec.get("id")


def problems(register, rec):
    out = []
    if register == "dependency_edges":
        for f in ("from", "to", "kind"):
            if not rec.get(f):
                out.append(f"missing {f}")
    else:
        field = "object_id" if register == "rationalization" else "id"
        rid = rec.get(field) or ""
        if not rid.startswith(PREFIX.get(register, ("",))):
            out.append(f"{field} {rid!r} does not start with {' / '.join(PREFIX.get(register, ()))}")
    if register in NEEDS_EVIDENCE:
        ev = rec.get("evidence") or []
        if not ev:
            out.append("no evidence — no locator, no record")
        for e in ev:
            if not e.get("locator"):
                out.append("evidence without a locator")
            if len(e.get("excerpt") or "") > EXCERPT_MAX:
                out.append(f"excerpt over {EXCERPT_MAX} chars")
    field = TEXT_MAX.get(register)
    if field and len(rec.get(field) or "") > 300:
        out.append(f"{field} over 300 chars — if it needs more, it is two records")
    return out


def load(src):
    text = sys.stdin.read() if src == "-" else Path(src).read_text()
    text = text.strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write(run_dir, register, records):
    if register not in PREFIX and register != "dependency_edges":
        raise SystemExit(f"unknown register {register!r}; one of {sorted(PREFIX) + ['dependency_edges']}")
    bad = {}
    for rec in records:
        p = problems(register, rec)
        if p:
            bad[key(register, rec)] = p
    if bad:
        for k, p in bad.items():
            print(f"REFUSED {k}: {'; '.join(p)}", file=sys.stderr)
        raise SystemExit(f"{len(bad)} of {len(records)} records refused; nothing written")
    path = Path(run_dir) / f"{register}.jsonl"
    existing = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                existing[key(register, r)] = r
    added = replaced = 0
    for rec in records:
        rec.setdefault("status", "extracted")
        k = key(register, rec)
        replaced += k in existing
        added += k not in existing
        existing[k] = rec
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing.values()))
    return added, replaced, len(existing)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 3:
        raise SystemExit(__doc__)
    run_dir, register, src = argv
    added, replaced, total = write(run_dir, register, load(src))
    print(f"{register}: +{added} new, {replaced} replaced, {total} in {Path(run_dir) / (register + '.jsonl')}")


if __name__ == "__main__":
    main()
