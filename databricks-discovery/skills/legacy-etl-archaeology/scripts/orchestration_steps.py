"""List every orchestration step a project's Synapse pipelines and Azure ML pipelines run — the
edges an assessment must not drop. Stdlib only.

    python3 orchestration_steps.py <project root>            # TSV on stdout
    python3 orchestration_steps.py <project root> --json

One row per step: from_kind, from_name, step, edge_kind, to_kind, to_name, locator.
Reads, wherever they sit under the root:
- Synapse pipelines in the Git shape (one `pipeline/<name>.json`, `properties.activities`,
  `typeProperties.*`) and the live-export shape (`az synapse pipeline list` — a JSON array, no
  `properties`, typeProperties flattened onto each activity), including nested activities.
- Azure ML pipeline YAML (`type: pipeline` with `jobs:`) — one `job` per step, named by the
  component's `name:` — and a live `az ml component list` export (JSON array of components).
Every row becomes one dependency_edges record (pipeline → procedure / notebook / pipeline / job).
"""
import json
import re
import sys
from pathlib import Path

NESTED = ("activities", "ifTrueActivities", "ifFalseActivities", "defaultActivities")
SKIP_DIRS = {".git", "node_modules", "assessment", ".velox"}


def tp(a, key):
    """A typeProperties field from either shape."""
    return (a.get("typeProperties") or {}).get(key, a.get(key))


def walk(acts):
    for a in acts or []:
        yield a
        for k in NESTED:
            yield from walk(tp(a, k))
        for case in tp(a, "cases") or []:
            yield from walk(case.get("activities"))


def ref_name(v):
    if isinstance(v, dict):
        return v.get("referenceName") or ref_name(v.get("value"))
    return v if isinstance(v, str) else None


def synapse_rows(name, acts, locator):
    for a in walk(acts):
        t, step = a.get("type"), a.get("name")
        if t in ("SqlPoolStoredProcedure", "SqlServerStoredProcedure"):
            yield ("pipeline", name, step, "calls", "procedure", ref_name(tp(a, "storedProcedureName")), locator)
        elif t == "SynapseNotebook":
            yield ("pipeline", name, step, "calls", "notebook", ref_name(tp(a, "notebook")), locator)
        elif t == "ExecutePipeline":
            yield ("pipeline", name, step, "calls", "pipeline", ref_name(tp(a, "pipeline")), locator)
        elif t == "SparkJob":
            yield ("pipeline", name, step, "calls", "spark_job", ref_name(tp(a, "sparkJob")), locator)
        elif t == "ExecuteDataFlow":
            yield ("pipeline", name, step, "calls", "dataflow", ref_name(tp(a, "dataflow")), locator)


def yaml_scalar(text, key):
    m = re.search(rf"^{key}:\s*['\"]?([^'\"\n#]+?)['\"]?\s*(#.*)?$", text, re.M)
    return m.group(1).strip() if m else None


def aml_pipeline_rows(path, root):
    """`type: pipeline` YAML: each step under `jobs:` (indented one level) is a job."""
    text = path.read_text(errors="replace")
    pname = yaml_scalar(text, "display_name") or yaml_scalar(text, "name") or path.stem
    block = re.search(r"^jobs:\s*\n((?:[ \t]+.*\n?|\s*\n)+)", text, re.M)
    if not block:
        return
    body = block.group(1)
    indent = min(len(m.group(1)) for m in re.finditer(r"^([ \t]+)\S", body, re.M))
    for m in re.finditer(rf"^[ \t]{{{indent}}}([A-Za-z0-9_\-]+):\s*$", body, re.M):
        step = m.group(1)
        rest = body[m.end():]
        nxt = re.search(rf"^[ \t]{{{indent}}}\S", rest, re.M)
        chunk = rest[: nxt.start()] if nxt else rest
        comp = re.search(r"component:\s*['\"]?([^'\"\s#]+)", chunk)
        job = step
        if comp and not comp.group(1).startswith("azureml:"):
            cfile = (path.parent / comp.group(1)).resolve()
            if cfile.is_file():
                job = yaml_scalar(cfile.read_text(errors="replace"), "name") or step
        elif comp:
            job = comp.group(1).removeprefix("azureml:").split(":")[0].split("@")[0]
        yield ("pipeline", pname, step, "calls", "job", job, f"{path.relative_to(root)}:jobs.{step}")


def aml_job_rows(jobs, components):
    """`az ml job list` pipeline jobs: one row per step, deduplicated across runs of the same pipeline."""
    seen = set()
    for o, loc in jobs:
        pname = o.get("display_name") or o.get("experiment_name") or o["name"]
        for step, j in o["jobs"].items():
            comp = str((j or {}).get("component") or "")
            name = comp.removeprefix("azureml:").split(":")[0].split("@")[0]
            if not name or name == "azureml_anonymous":
                # ponytail: an inline step has no registered name; match `<prefix>_<step>` in the
                # component list, else keep the step key. `az ml job show` would name it exactly.
                name = next((c for c in sorted(components) if c == step or c.endswith("_" + step)), step)
            if (pname, step) not in seen:
                seen.add((pname, step))
                yield ("pipeline", pname, step, "calls", "job", name, f"{loc}:jobs.{step}")


def scan(root):
    root = Path(root)
    rows, aml_jobs, components = [], [], set()
    for p in sorted(root.rglob("*")):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        loc = str(p.relative_to(root))
        if p.suffix == ".json":
            try:
                doc = json.loads(p.read_text(errors="replace"))
            except ValueError:
                continue
            objs = doc if isinstance(doc, list) else [doc]
            for i, o in enumerate(objs):
                if not isinstance(o, dict):
                    continue
                props = o.get("properties") if isinstance(o.get("properties"), dict) else o
                if "activities" in props and o.get("name"):
                    where = f"{loc}[{i}]" if isinstance(doc, list) else loc
                    rows += synapse_rows(o["name"], props["activities"], where)
                elif o.get("type") == "pipeline" and isinstance(o.get("jobs"), dict):
                    aml_jobs.append((o, f"{loc}[{i}]" if isinstance(doc, list) else loc))
                elif isinstance(doc, list) and "creation_context" in o and "/components/" in str(o.get("id", "")):
                    components.add(o["name"])  # az ml component list
        elif p.suffix in (".yml", ".yaml"):
            text = p.read_text(errors="replace")
            if re.search(r"^type:\s*pipeline\s*$", text, re.M):
                rows += aml_pipeline_rows(p, root)
    rows += aml_job_rows(aml_jobs, components)
    return list(dict.fromkeys(rows))


COLS = ("from_kind", "from_name", "step", "edge_kind", "to_kind", "to_name", "locator")

if __name__ == "__main__":
    out = scan(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps([dict(zip(COLS, r)) for r in out], indent=1))
    else:
        print("\t".join(COLS))
        for r in out:
            print("\t".join(str(x) for x in r))
        print(f"# {len(out)} steps", file=sys.stderr)
