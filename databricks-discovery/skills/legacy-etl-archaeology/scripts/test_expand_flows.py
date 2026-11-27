"""python3 test_expand_flows.py — offline self-check of expand_flows.py."""
import json
import tempfile
from pathlib import Path

import expand_flows as x

w = x.write_records
EV = [{"source_id": "src-01", "locator": "sources/nb.json:3", "excerpt": "cfg['sink']", "kind": "stated"}]


def cfg(**kv):
    return json.dumps(kv, indent=2)


def listed(summary, key):
    """A summary list as the script prints it: its count and its first ten (review of #17, 5,000 rows)."""
    got = summary[key]
    assert set(got) == {"count", "first"} and len(got["first"]) == min(got["count"], 10), got
    return got["first"]


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
        assert listed(s, "disabled") == ["obj-0001-erp-customers"] and listed(s, "by_query") == ["obj-0001-by-query"]
        assert listed(s, "skipped") == ["sources/config/_defaults.json:1"]
        assert "erp.dbo.Orders" in listed(s, "unmatched") and "bronze.orders" not in listed(s, "unmatched")
        assert listed(s, "unrouted") == []
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
        assert (s["flows"], s["new"], s["replaced"]) == (3, 1, 2) and listed(s, "gone") == ["obj-0001-f0", "obj-0001-old"]
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


def test_an_entry_no_description_routes_is_counted_never_dropped():
    # Review of #17: a control table routed 'H' / 'D' with a 'W' row lost that row without a word.
    weekly = CSV + "w1,s.w1,b.w1,W,1,Server=x;Password=Synthetic1\n"
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/ctl.csv": weekly}, [routed("H", "obj-0010", "hourly"), routed("D", "obj-0011", "daily")],
                            runner_extra={"kind": "pipeline", "name": "PL_Copy_One"})
        s = x.expand(run, "obj-0001")
        assert s["flows"] == 3 and listed(s, "unrouted") == ["sources/ctl.csv:5"], s
        assert "obj-0001-w1" not in {r["id"] for r in rows(run, "inventory")}            # no flow: nobody runs it here
    with tempfile.TemporaryDirectory() as d:
        # Runners split by type: another runner's description over the same entries takes the 'W' row.
        other = {**obj("obj-0005", "pipeline", "PL_Copy_Weekly"), "framework": routed("W", None, "weekly")}
        root, run = project(d, {"sources/ctl.csv": weekly}, [routed("H", "obj-0010", "hourly"), routed("D", "obj-0011", "daily")],
                            runner_extra={"kind": "pipeline", "name": "PL_Copy_One"}, inventory=[other])
        assert listed(x.expand(run, "obj-0001"), "unrouted") == []


def test_a_long_list_gives_its_count_and_first_ten():
    # Review of #17: 5,000 rows gave 1,667 + 10,000 review items, one per flow.
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/f{i:02}.json": cfg(name=f"f{i:02}", src=f"s.t{i}", tgt=f"b.t{i}", active=0) for i in range(25)}
        root, run = project(d, files, fw(fields={"source": "src", "target": "tgt", "enabled": "active"}))
        s = x.expand(run, "obj-0001")
        assert s["disabled"] == {"count": 25, "first": [f"obj-0001-f{i:02}" for i in range(10)]}, s["disabled"]
        assert s["unmatched"]["count"] == 50 and len(s["unmatched"]["first"]) == 10
        assert len(s["files"]) == 25                                                     # the files stay whole: manifest.json lists them
        assert sum(1 for r in rows(run, "inventory") if r.get("runner")) == 25           # every flow is still written


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
        assert s["flows"] == 2 and listed(s, "incomplete") == ["obj-0001-a", "obj-0001-b"]


def test_numeric_key():
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/ctl.csv": "FlowId,Src,Sink\n17,s.a,b.a\n"},
                            fw(entries={"format": "csv", "path": "sources/ctl.csv"}, key="FlowId", fields={"source": "Src", "target": "Sink"}))
        x.expand(run, "obj-0001")
        flow = next(r for r in rows(run, "inventory") if r.get("runner"))
        assert (flow["id"], flow["name"]) == ("obj-0001-17", "17")


def test_cli_prints_the_summary():
    import subprocess
    import sys
    with tempfile.TemporaryDirectory() as d:
        root, run = project(d, {"sources/config/a.json": cfg(name="a", src="s", tgt="t")}, fw())
        out = subprocess.run([sys.executable, str(Path(x.__file__)), "expand", str(run), "obj-0001"],
                             check=True, capture_output=True, text=True).stdout
        assert json.loads(out)["flows"] == 1


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


def test_decide_note_is_the_reason_on_every_flow_decided_by_default():
    import subprocess
    import sys
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}", active=a) for n, a in (("a", 1), ("b", 1), ("c", 0))}
        root, run = project(d, files, fw(fields={"source": "src", "target": "tgt", "enabled": "active"}))
        x.expand(run, "obj-0001")
        note = "a Copy has no runner to move; keep is the option if the copy stays in Data Factory"
        x.decide(run, "obj-0001", "rewrite", {"obj-0001-b": "convert"}, note=note)
        rat = {r["object_id"]: r for r in rows(run, "rationalization")}
        assert rat["obj-0001-a"]["notes"] == note
        assert rat["obj-0001-b"]["notes"] is None                      # an exception is not the default's reason
        assert "owner confirms" in rat["obj-0001-c"]["notes"]           # a disabled flow keeps its own note
        out = subprocess.run([sys.executable, str(Path(x.__file__)), "decide", str(run), "obj-0001", "convert",
                              "--note", "carried as configuration"], check=True, capture_output=True, text=True).stdout
        assert json.loads(out)["runner"] == "convert"
        assert {r["object_id"]: r for r in rows(run, "rationalization")}["obj-0001-a"]["notes"] == "carried as configuration"


def test_a_gone_flow_gets_no_decision():
    # Review of #17: delete an entry, expand reports it gone, and decide still wrote `convert` for it.
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}") for n in ("a", "b", "c")}
        root, run = project(d, files, fw())
        x.expand(run, "obj-0001")
        (root / "sources/config/c.json").unlink()
        assert listed(x.expand(run, "obj-0001"), "gone") == ["obj-0001-c"]
        s = x.decide(run, "obj-0001", "convert", {})
        assert s["flows"] == 2 and "obj-0001-c" not in {r["object_id"] for r in rows(run, "rationalization")}, s
        assert_refused(lambda: x.decide(run, "obj-0001", "convert", {"obj-0001-c": "keep"}), "obj-0001-c")


def test_a_gone_flow_that_was_already_decided_is_listed_for_rejection():
    # Hieu's re-check of #17: expand, decide, delete c.json, expand, decide left `obj-0001-c: convert` in the
    # rationalization. Nothing is deleted, so decide names the gone flows that already have a decision.
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}") for n in ("a", "b", "c")}
        root, run = project(d, files, fw())
        x.expand(run, "obj-0001")
        assert listed(x.decide(run, "obj-0001", "convert", {}), "gone_decided") == []
        (root / "sources/config/c.json").unlink()
        x.expand(run, "obj-0001")
        s = x.decide(run, "obj-0001", "convert", {})
        assert s["flows"] == 2 and listed(s, "gone_decided") == ["obj-0001-c"], s
        assert {r["object_id"]: r["disposition"] for r in rows(run, "rationalization")}["obj-0001-c"] == "convert"  # kept
    with tempfile.TemporaryDirectory() as d:                         # a decision already reviewed into the registers
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}") for n in ("a", "b")}
        root, run = project(d, files, fw())
        reg = run.parents[1] / "registers"
        reg.mkdir()
        old = {"id": "obj-0001-old", "kind": "pipeline", "name": "old", "runner": "obj-0001", "status": "reviewed"}
        (reg / "inventory.jsonl").write_text(json.dumps(old) + "\n")
        (reg / "rationalization.jsonl").write_text(json.dumps(
            {"object_id": "obj-0001-old", "kind": "pipeline", "disposition": "convert", "status": "reviewed"}) + "\n")
        x.expand(run, "obj-0001")
        assert listed(x.decide(run, "obj-0001", "convert", {}), "gone_decided") == ["obj-0001-old"]


def test_two_runners_over_one_table_list_an_unrouted_row_once():
    # Hieu's re-check of #17: both runners reported the same 'W' row, so review.md listed it twice.
    weekly = CSV + "w1,s.w1,b.w1,W,1,Server=x;Password=Synthetic1\n"
    with tempfile.TemporaryDirectory() as d:
        other = {**obj("obj-0005", "pipeline", "PL_Copy_Daily"), "framework": routed("D", "obj-0011", "daily")}
        root, run = project(d, {"sources/ctl.csv": weekly}, routed("H", "obj-0010", "hourly"),
                            runner_extra={"kind": "pipeline", "name": "PL_Copy_Hourly"}, inventory=[other])
        assert listed(x.expand(run, "obj-0001"), "unrouted") == ["sources/ctl.csv:5"]     # the lowest id reports it
        assert listed(x.expand(run, "obj-0005"), "unrouted") == []                       # the other does not


def test_a_runner_retired_while_its_flows_are_rewritten_waits_for_them():
    # Bartosz, 2026-11-25 (review of #17): rewrites land in waves, and the old runner keeps loading
    # the flows not yet rewritten, so its retire says when.
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}", active=a) for n, a in (("a", 1), ("b", 1), ("c", 0))}
        root, run = project(d, files, fw(fields={"source": "src", "target": "tgt", "enabled": "active"}, dispatcher="obj-0002"),
                            inventory=[obj("obj-0002", "pipeline", "PL_All")])
        x.expand(run, "obj-0001")
        x.decide(run, "obj-0001", "rewrite", {})
        rat = {r["object_id"]: r for r in rows(run, "rationalization")}
        for oid in ("obj-0001", "obj-0002"):
            assert rat[oid]["disposition"] == "retire"
            assert rat[oid]["target_component"] == "stays in the source until the last rewrite is live", rat[oid]
            assert rat[oid]["notes"] == "Retire after its 2 rewritten flows run in Databricks; until then it keeps running in the source"
    with tempfile.TemporaryDirectory() as d:                         # every flow retired: nothing to wait for
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}", active=0) for n in ("a", "b", "c")}
        root, run = project(d, files, fw(fields={"source": "src", "target": "tgt", "enabled": "active"}))
        x.expand(run, "obj-0001")
        x.decide(run, "obj-0001", "rewrite", {})
        runner = {r["object_id"]: r for r in rows(run, "rationalization")}["obj-0001"]
        assert (runner["disposition"], runner["target_component"], runner["notes"]) == ("retire", None, "follows its 3 flows"), runner


def test_a_flow_rejected_in_the_registers_stays_out_of_decide():
    with tempfile.TemporaryDirectory() as d:
        files = {f"sources/config/{n}.json": cfg(name=n, src=f"s.{n}", tgt=f"bronze.{n}") for n in ("a", "junk")}
        root, run = project(d, files, fw())
        x.expand(run, "obj-0001")                                   # the run proposes both again
        reg = run.parents[1] / "registers"
        reg.mkdir()
        rejected = {**next(r for r in rows(run, "inventory") if r["id"] == "obj-0001-junk"), "status": "rejected"}
        (reg / "inventory.jsonl").write_text(json.dumps(rejected) + "\n")
        s = x.decide(run, "obj-0001", "convert", {})
        assert s["flows"] == 1 and "obj-0001-junk" not in {r["object_id"] for r in rows(run, "rationalization")}


FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures"


def fixture_project(tmp, name, framework, runner_extra=None, inventory=()):
    import shutil
    root = Path(tmp)
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
        assert (s["flows"], s["disabled"]["count"], s["by_query"]["count"]) == (7, 1, 1), s
        assert listed(s, "skipped") == ["sources/config/ingest/_defaults.json:1"], s
        assert listed(s, "incomplete") == [] and listed(s, "unrouted") == [], s
        writes = [t for r in rows(run, "inventory") if r.get("runner") for t in r["writes"]]
        assert len(writes) == 7 and not any(t.startswith("stg_") for t in writes), writes


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
        assert (s["flows"], s["disabled"]["count"], s["by_query"]["count"]) == (10, 2, 10), s
        assert listed(s, "unrouted") == ["sources/exports/ctl_IngestControl.csv:12"], s     # fin_budget, 'W': nobody routes it
        flows = [r for r in rows(run, "inventory") if r.get("runner")]
        assert sum(1 for r in flows if r["writes"] == ["bronze.crm_contacts"]) == 2
        text = "".join((run / f).read_text() for f in ("inventory.jsonl", "dependency_edges.jsonl"))
        assert "Password" not in text and "TargetTable_Old" not in text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
