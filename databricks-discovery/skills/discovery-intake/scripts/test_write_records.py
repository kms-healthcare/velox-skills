"""python3 test_write_records.py — offline self-check."""
import json
import tempfile
from pathlib import Path

import write_records as w

EV = [{"source_id": "src-01", "locator": "a.py:3", "excerpt": "x", "kind": "stated"}]
# Every reviewed record explains itself; the fixtures carry the fields so the other tests stay about their own rule.
EXPLAIN = {"meaning": "what it is", "impact": "what accepting it means", "risk": "if we are wrong",
           "recommendation": {"decision": "accept", "reason": "evidence matches the code", "confidence": "high"}}


def test_upsert_by_id_and_defaults():
    with tempfile.TemporaryDirectory() as d:
        a = w.write(d, "findings", [{"id": "FND-01", "title": "a", "evidence": EV, **EXPLAIN}])
        b = w.write(d, "findings", [{"id": "FND-01", "title": "a2", "evidence": EV, **EXPLAIN}, {"id": "FND-02", "title": "b", "evidence": EV, **EXPLAIN}])
        assert a == (1, 0, 1) and b == (1, 1, 2)
        rows = [json.loads(x) for x in (Path(d) / "findings.jsonl").read_text().splitlines()]
        assert [r["id"] for r in rows] == ["FND-01", "FND-02"] and rows[0]["title"] == "a2"
        assert all(r["status"] == "extracted" for r in rows)
        e = w.write(d, "dependency_edges", [{"from": "obj-1", "to": "obj-2", "kind": "writes", "evidence": EV, "meaning": "the load writes the table", "recommendation": EXPLAIN["recommendation"]}] * 2)
        assert e == (1, 1, 1)                                             # edges key on from|to|kind
        r = w.write(d, "rationalization", [{"object_id": "obj-1", "disposition": "migrate"},
                                           {"object_id": "obj-1", "disposition": "retire"}])
        assert r == (1, 1, 1)                                             # rationalization keys on object_id


def test_refuses_bad_records_and_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        for rec in (
            {"id": "X-01", "evidence": EV, **EXPLAIN},                     # wrong prefix
            {"id": "FND-01", **EXPLAIN},                                  # no evidence
            {"id": "FND-01", "evidence": [{"source_id": "s", "excerpt": "x"}], **EXPLAIN},   # no locator
            {"id": "FND-01", "evidence": [{"locator": "a", "excerpt": "y" * 121}], **EXPLAIN},
            {"id": "FND-01", "evidence": EV, "detail": "z" * 301, **EXPLAIN},
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


def test_source_systems_named_never_signed_in():
    with tempfile.TemporaryDirectory() as d:
        ok = {"id": "SYS-1", "name": "orders", "engine": "postgresql", "host": "pg-prod.client.local", "port": 5432,
              "database": "orders", "evidence": [{"locator": "etl/load_orders.py:1", "excerpt": "host='pg-prod.client.local'"}], **EXPLAIN}
        assert w.write(d, "source_systems", [ok]) == (1, 0, 1)
        for bad, why in (
            ({**ok, "id": "SRC-1"}, "does not start with SYS-"),
            ({**ok, "engine": None}, "missing engine"),
            ({**ok, "user": "etl_ro"}, "user holds a credential"),
            ({**ok, "password": "x"}, "password holds a credential"),
            ({**ok, "connection": {"token": "dapi1234567890"}}, "connection.token holds a credential"),
            ({**ok, "notes": "pwd=hunter2 in config"}, "notes looks like a credential"),
            ({**ok, "evidence": [{"locator": "cfg.py:3", "excerpt": "postgres://etl:hunter2@pg-prod/orders"}]}, "evidence.0.excerpt looks like a credential"),
        ):
            try:
                w.write(d, "source_systems", [bad])
            except SystemExit as e:
                assert "refused" in str(e)
            else:
                raise AssertionError(f"accepted {bad}")
            assert any(why in p for p in w.problems("source_systems", bad)), (why, w.problems("source_systems", bad))
        rows = (Path(d) / "source_systems.jsonl").read_text().splitlines()
        assert len(rows) == 1 and json.loads(rows[0])["id"] == "SYS-1"   # the refusals wrote nothing
        # the host and a plain locator are not credentials
        assert w.problems("source_systems", {**ok, "host": "sql.client.local\\PROD", "evidence": [{"locator": "appsettings.json:12"}]}) == []
        # every inventory object names its system
        assert w.problems("inventory", {"id": "obj-1", "kind": "table", "name": "t", "evidence": EV, **EXPLAIN}) == [
            "missing system (SYS-<n>) — every object belongs to a source system"]
        assert w.problems("inventory", {"id": "obj-1", "kind": "table", "name": "t", "system": "SYS-1", "evidence": EV, **EXPLAIN}) == []


def test_every_reviewed_record_explains_itself():
    base = {"id": "FND-01", "title": "t", "evidence": EV}
    assert w.problems("findings", {**base, **EXPLAIN}) == []
    missing = w.problems("findings", base)
    assert "missing meaning — a reviewer must not have to guess" in missing
    assert "missing impact — a reviewer must not have to guess" in missing
    assert "missing risk — a reviewer must not have to guess" in missing
    assert "missing recommendation {decision, reason, confidence}" in missing
    long = w.problems("findings", {**base, **EXPLAIN, "meaning": "m" * 161})
    assert long == ["meaning over 160 chars"]
    bad_rec = w.problems("findings", {**base, **EXPLAIN, "recommendation": {"decision": "approve", "reason": "", "confidence": 0.8}})
    assert bad_rec == ["recommendation.decision must be one of accept / reject / defer",
                       "missing recommendation.reason",
                       "recommendation.confidence must be one of high / medium / low — a word, never a number"]
    # a plain fact — an inventory object, an edge — needs a meaning; impact, risk and the recommendation are optional
    edge = {"from": "obj-1", "to": "obj-2", "kind": "writes", "evidence": EV, "meaning": "x"}
    assert w.problems("dependency_edges", edge) == []
    assert w.problems("dependency_edges", {k: v for k, v in edge.items() if k != "meaning"}) == ["missing meaning — a reviewer must not have to guess"]
    obj = {"id": "obj-1", "kind": "table", "name": "t", "system": "SYS-1", "evidence": EV, "meaning": "the orders table"}
    assert w.problems("inventory", obj) == []
    assert w.problems("inventory", {**obj, "recommendation": {"decision": "accept"}}) == [
        "missing recommendation.reason",
        "recommendation.confidence must be one of high / medium / low — a word, never a number"]   # given, it is checked
    # synthesis registers are not reviewed record by record: nothing required
    assert w.problems("readiness", {"id": "RDY-data", "score": 2}) == []
    assert w.problems("rationalization", {"object_id": "obj-1", "disposition": "migrate"}) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
