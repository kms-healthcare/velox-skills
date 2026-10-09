"""python3 test_write_records.py — offline self-check."""
import json
import tempfile
from pathlib import Path

import write_records as w

EV = [{"source_id": "src-01", "locator": "a.py:3", "excerpt": "x", "kind": "stated"}]


def test_upsert_by_id_and_defaults():
    with tempfile.TemporaryDirectory() as d:
        a = w.write(d, "findings", [{"id": "FND-01", "title": "a", "evidence": EV}])
        b = w.write(d, "findings", [{"id": "FND-01", "title": "a2", "evidence": EV}, {"id": "FND-02", "title": "b", "evidence": EV}])
        assert a == (1, 0, 1) and b == (1, 1, 2)
        rows = [json.loads(x) for x in (Path(d) / "findings.jsonl").read_text().splitlines()]
        assert [r["id"] for r in rows] == ["FND-01", "FND-02"] and rows[0]["title"] == "a2"
        assert all(r["status"] == "extracted" for r in rows)
        e = w.write(d, "dependency_edges", [{"from": "obj-1", "to": "obj-2", "kind": "writes", "evidence": EV}] * 2)
        assert e == (1, 1, 1)                                             # edges key on from|to|kind
        r = w.write(d, "rationalization", [{"object_id": "obj-1", "disposition": "migrate"},
                                           {"object_id": "obj-1", "disposition": "retire"}])
        assert r == (1, 1, 1)                                             # rationalization keys on object_id


def test_refuses_bad_records_and_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        for rec in (
            {"id": "X-01", "evidence": EV},                                # wrong prefix
            {"id": "FND-01"},                                             # no evidence
            {"id": "FND-01", "evidence": [{"source_id": "s", "excerpt": "x"}]},   # no locator
            {"id": "FND-01", "evidence": [{"locator": "a", "excerpt": "y" * 121}]},
            {"id": "FND-01", "evidence": EV, "detail": "z" * 301},
        ):
            try:
                w.write(d, "findings", [rec])
            except SystemExit as e:
                assert "refused" in str(e)
            else:
                raise AssertionError(f"accepted {rec}")
        assert not (Path(d) / "findings.jsonl").exists()
        assert w.problems("readiness", {"id": "RDY-data", "score": 2}) == []   # synthesis registers carry no evidence
        assert w.problems("rationalization", {"id": "obj-1"}) == ["object_id '' does not start with obj-"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
