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


def test_inventory_kinds_are_the_three_layers_and_one_record_per_object():
    obj = {"id": "obj-1", "kind": "table", "name": "bronze.orders", "system": "SYS-1", "evidence": EV, "meaning": "m"}
    assert w.problems("inventory", obj) == []
    assert w.problems("inventory", {**obj, "kind": "job", "name": "eurostream transform (ingest, pii_scan and build)"}) == []   # a workload may name its steps
    assert w.problems("inventory", {**obj, "kind": "model", "name": "churn:3"}) == []                                   # a registered model is data the move reaches
    bad = w.problems("inventory", {**obj, "kind": "rest_call"})
    assert len(bad) == 1 and bad[0].startswith("kind 'rest_call' is not one of table / view")
    bundled = w.problems("inventory", {**obj, "kind": "topic", "name": "Kafka topics orders, clicks, payments"})
    assert bundled == ["one record per object: 'Kafka topics orders, clicks, payments' names several — write one record each"]
    assert w.problems("rationalization", {"object_id": "obj-1", "disposition": "repoint"}) == []
    assert w.problems("rationalization", {"object_id": "obj-1", "disposition": "maybe"}) == [
        "disposition 'maybe' is not one of migrate / modernize / retire / defer / convert / rewrite / keep / repoint / replace"]


def test_rule_status_verified_only_against_code():
    rule = {"id": "BR-01", "name": "Net revenue", "logic": "status <> 9", "plain": "test data never counts", **EXPLAIN}
    doc = [{"source_id": "src-kpi", "source_type": "spec", "locator": "KPI_definitions.docx p.4 §2.1", "kind": "stated"}]
    code = [{"source_id": "src-sp-014", "locator": "sp_Calc_Daily_Revenue.sql:45", "kind": "stated"}]
    with tempfile.TemporaryDirectory() as d:
        for bad, why in (
            ({**rule, "rule_status": "VERIFIED", "evidence": doc}, "is DOC-ONLY until it is matched to code"),                       # a document is not the code
            ({**rule, "rule_status": "VERIFIED", "evidence": [{"locator": "kpi.md:12"}]}, "is DOC-ONLY until it is matched to code"),
            ({**rule, "rule_status": "CONFIRMED", "evidence": code}, "rule_status 'CONFIRMED' is not one of"),
            ({**rule, "evidence": code}, "rule_status None is not one of"),
        ):
            try:
                w.write(d, "business_rules", [bad])
            except SystemExit as e:
                assert "refused" in str(e)
            else:
                raise AssertionError(f"accepted {bad}")
            assert any(why in p for p in w.problems("business_rules", bad)), (why, w.problems("business_rules", bad))
        assert not (Path(d) / "business_rules.jsonl").exists()
        # matched to code: VERIFIED stands — by locator, or by source_type when the locator is an object name
        assert w.problems("business_rules", {**rule, "rule_status": "VERIFIED", "evidence": doc + code}) == []
        assert w.problems("business_rules", {**rule, "rule_status": "VERIFIED", "evidence": [
            {"source_type": "code", "locator": "dbo.sp_Calc_Daily_Revenue"}]}) == []
        assert w.write(d, "business_rules", [{**rule, "rule_status": "VERIFIED", "evidence": code},
                                             {**rule, "id": "BR-02", "rule_status": "DOC-ONLY", "evidence": doc}]) == (2, 0, 2)


def test_a_saving_is_a_number():
    base = {"id": "FND-1", "evidence": EV, **EXPLAIN}
    assert w.problems("findings", {**base, "saving": {"amount": 43, "currency": "USD", "per": "day"}}) == []
    assert w.problems("findings", {**base, "saving": None}) == []
    assert w.problems("findings", {**base, "saving": {"amount": "43"}}) == ['saving.amount \'43\' must be a number (43, not "43")']


def test_a_draft_inside_the_run_is_consumed_and_one_outside_is_kept():
    # Measured 2026-11-12: eight drafts left under <run>/tools/ beside the registers they fed.
    rec = [{"id": "FND-01", "title": "a", "evidence": EV, **EXPLAIN}]
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
        run = Path(d) / "runs" / "2026-11-12_run-01-m"
        (run / "tools").mkdir(parents=True)
        draft = run / "tools" / "findings.json"
        draft.write_text(json.dumps(rec))
        w.main([str(run), "findings", str(draft)])
        assert not draft.exists() and not (run / "tools").exists()
        assert (run / "findings.jsonl").exists()                          # the records are kept
        mine = Path(out) / "findings.json"                                # not the run's: the caller's
        mine.write_text(json.dumps(rec))
        w.main([str(run), "findings", str(mine)])
        assert mine.exists()
        w.main([str(run), "findings", str(run / "findings.jsonl")])        # the register itself stays
        assert (run / "findings.jsonl").exists()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
