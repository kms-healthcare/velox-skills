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
