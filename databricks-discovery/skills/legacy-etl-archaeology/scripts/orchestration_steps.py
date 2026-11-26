"""List every orchestration step a project's Synapse pipelines and Azure ML pipelines run — the
edges an assessment must not drop. Stdlib only.

    python3 orchestration_steps.py <project root>            # TSV on stdout
    python3 orchestration_steps.py <project root> --json

One row per (pipeline, step, target): from_kind, from_name, step, edge_kind, to_kind, to_name,
unresolved, locator. `unresolved` is empty when the target is known; otherwise it holds the
expression (`@item().proc` — to_name is then empty) or the ambiguous candidates. A step seen in
both a Git and a live export is one row, its locators joined with `; `.
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


def target(v):
    """(name, unresolved): a reference or plain name, `[ctl].[usp_Log]` → `ctl.usp_Log`;
    an expression gives no name and is returned as unresolved."""
    if isinstance(v, dict):
        if v.get("type") == "Expression" or str(v.get("value", "")).startswith("@"):
            return None, str(v.get("value"))
        return target(v.get("referenceName") or v.get("value"))
    if not isinstance(v, str) or not v:
        return None, ""
    if v.startswith("@"):
        return None, v
    return re.sub(r"[\[\]\"`]", "", v), ""


# activity type → (to_kind, where the target sits: typeProperties key or (key, subkey))
STEPS = {
    "SqlPoolStoredProcedure": [("procedure", "storedProcedureName")],
    "SqlServerStoredProcedure": [("procedure", "storedProcedureName")],
    "Lookup": [("procedure", ("source", "sqlReaderStoredProcedureName"))],
    "Copy": [("procedure", ("source", "sqlReaderStoredProcedureName")),
             ("procedure", ("sink", "sqlWriterStoredProcedureName"))],
    "SynapseNotebook": [("notebook", "notebook")],
    "DatabricksNotebook": [("notebook", "notebookPath")],
    "ExecutePipeline": [("pipeline", "pipeline")],
    # Azure ML (v1 published pipeline): the id joins the az ml export, not a display name
    "AzureMLExecutePipeline": [("pipeline", "mlPipelineEndpointId"), ("pipeline", "mlPipelineId")],
    "SparkJob": [("spark_job", "sparkJob")],
    "ExecuteDataFlow": [("dataflow", "dataflow")],
}


def synapse_rows(name, acts, locator):
    for a in walk(acts):
        step = a.get("name")
        for kind, where in STEPS.get(a.get("type"), []):
            v = (tp(a, where[0]) or {}).get(where[1]) if isinstance(where, tuple) else tp(a, where)
            if v is None:
                continue
            to, unresolved = target(v)
            yield ("pipeline", name, step, "calls", kind, to or "", unresolved, locator)
            if a.get("type") == "AzureMLExecutePipeline":
                break  # endpoint id when set, else the pipeline id


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
        yield ("pipeline", pname, step, "calls", "job", job, "", f"{path.relative_to(root)}:jobs.{step}")


def aml_job_rows(jobs, components):
    """`az ml job list` pipeline jobs: one row per step, deduplicated across runs of the same pipeline."""
    seen = set()
    for o, loc in jobs:
        pname = o.get("display_name") or o.get("experiment_name") or o["name"]
        for step, j in o["jobs"].items():
            comp = str((j or {}).get("component") or "")
            name, unresolved = comp.removeprefix("azureml:").split(":")[0].split("@")[0], ""
            if not name or name == "azureml_anonymous":
                # ponytail: an inline step has no registered name; match `<prefix>_<step>` in the
                # component list. `az ml job show` would name it exactly.
                hits = [c for c in sorted(components) if c == step] or \
                       [c for c in sorted(components) if c.endswith("_" + step)]
                name = hits[0] if len(hits) == 1 else step
                unresolved = "ambiguous: " + " | ".join(hits) if len(hits) > 1 else ""
            if (pname, step) not in seen:
                seen.add((pname, step))
                yield ("pipeline", pname, step, "calls", "job", name, unresolved, f"{loc}:jobs.{step}")


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
    merged = {}  # one row per (pipeline, step, target); a Git and a live copy keep both locators
    for r in rows:
        locs = merged.setdefault(r[:7], [])
        if r[7] not in locs:
            locs.append(r[7])
    return [k + ("; ".join(v),) for k, v in merged.items()]


COLS = ("from_kind", "from_name", "step", "edge_kind", "to_kind", "to_name", "unresolved", "locator")

if __name__ == "__main__":
    out = scan(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps([dict(zip(COLS, r)) for r in out], indent=1))
    else:
        print("\t".join(COLS))
        for r in out:
            print("\t".join(str(x) for x in r))
        print(f"# {len(out)} steps", file=sys.stderr)
