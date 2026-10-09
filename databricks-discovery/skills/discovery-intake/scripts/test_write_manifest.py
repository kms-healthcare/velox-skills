"""python3 test_write_manifest.py — offline self-check."""
import hashlib
import json
import tempfile
from pathlib import Path

import write_manifest as w


def tree(d):
    root = Path(d)
    run = root / "discovery" / "p" / "runs" / "2026-10-09_run-01"
    (run / "logs").mkdir(parents=True)
    (run / "logs" / "exec-01-pytest.log").write_text("ok")
    (root / "src" / "__pycache__").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n")
    (root / "src" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    (run / "findings.jsonl").write_text('{"id":"FND-01"}\n{"id":"FND-02"}\n')
    # what posture.py leaves behind: its own source and the calls it made
    (run / "manifest.json").write_text(json.dumps({"run_id": run.name, "external_access": [{"endpoint": "GET /x"}],
                                                   "sources_read": [{"source_id": "src-client-posture", "path": "p.json"}]}))
    return root, run


def test_hashes_merges_and_counts():
    with tempfile.TemporaryDirectory() as d:
        root, run = tree(d)
        ex = [{"command": "pytest -q", "cwd": ".", "exit": 0, "log": "runs/2026-10-09_run-01/logs/exec-01-pytest.log"}]
        n, counts = w.write(run, {"sources": {"src-code": ["src"]}, "executions": ex, "model": "m"})
        m = json.loads((run / "manifest.json").read_text())
        assert n == 1 and counts == {"findings": 2}                      # __pycache__ skipped
        assert m["project"] == "p" and m["model"] == "m" and m["executions"] == ex
        assert m["external_access"] == [{"endpoint": "GET /x"}]           # posture's calls kept
        ids = [s["source_id"] for s in m["sources_read"]]
        assert ids == ["src-client-posture", "src-code"]
        assert m["sources_read"][1] == {"source_id": "src-code", "path": "src/a.py",
                                        "sha256": hashlib.sha256(b"x = 1\n").hexdigest(), "bytes": 6}
        w.write(run, {"sources": {"src-code": ["src/a.py"]}})              # same id again replaces, not duplicates
        w.write(run, {"executions": [dict(ex[0], log="discovery/p/" + ex[0]["log"])]})   # log from the project root too
        assert len(json.loads((run / "manifest.json").read_text())["sources_read"]) == 2


def test_refuses_and_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        root, run = tree(d)
        before = (run / "manifest.json").read_text()
        for fields in ({"sources": {"src-x": ["nope"]}},
                       {"executions": [{"command": "pytest", "exit": 0, "log": "missing.log"}]},
                       {"executions": [{"command": "pytest"}]}):
            try:
                w.write(run, fields)
            except SystemExit as e:
                assert "not written" in str(e)
            else:
                raise AssertionError(f"accepted {fields}")
        assert (run / "manifest.json").read_text() == before
        try:
            w.write(root / "src", {})
        except SystemExit as e:
            assert "is not discovery" in str(e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
