"""python -m pytest -q — offline self-check for orchestration_steps.py (synthetic names only)."""
import json
import tempfile
from pathlib import Path

import orchestration_steps as o

LOG = {"name": "Log", "type": "SqlPoolStoredProcedure", "sqlPool": {"referenceName": "pool"}}


def test_git_and_live_shapes_give_the_same_edges():
    git_act = dict(LOG, typeProperties={"storedProcedureName": "ctl.usp_Log"})
    live_act = dict(LOG, storedProcedureName="ctl.usp_Log")
    loop = {"name": "Each", "type": "ForEach", "typeProperties": {"activities": [
        {"name": "Run", "type": "ExecutePipeline", "typeProperties": {"pipeline": {"referenceName": "PL_Child"}}}]}}
    live_loop = {"name": "Each", "type": "ForEach", "activities": [
        {"name": "Run", "type": "ExecutePipeline", "pipeline": {"referenceName": "PL_Child", "type": "PipelineReference"}}]}
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "git/pipeline").mkdir(parents=True)
        (root / "git/pipeline/PL_A.json").write_text(json.dumps({"name": "PL_A", "properties": {"activities": [loop, git_act]}}))
        (root / "live").mkdir()
        (root / "live/pipeline.json").write_text(json.dumps([{"name": "PL_A", "activities": [live_loop, live_act]}]))
        rows = o.scan(root)
    git = {r[:6] for r in rows if r[6].startswith("git")}
    live = {r[:6] for r in rows if r[6].startswith("live")}
    assert git == live == {
        ("pipeline", "PL_A", "Run", "calls", "pipeline", "PL_Child"),
        ("pipeline", "PL_A", "Log", "calls", "procedure", "ctl.usp_Log"),
    }


def test_if_condition_branches_are_walked():
    act = {"name": "If", "type": "IfCondition", "ifTrueActivities": [dict(LOG, storedProcedureName="ops.usp_Purge")]}
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "p.json").write_text(json.dumps([{"name": "PL_B", "activities": [act]}]))
        assert [r[5] for r in o.scan(d)] == ["ops.usp_Purge"]


def test_azure_ml_pipeline_steps_are_jobs_named_by_component():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "ml/components/prep").mkdir(parents=True)
        (root / "ml/components/prep/prep.yml").write_text("name: demo_prep\ntype: command\n")
        (root / "ml/pipeline.yml").write_text(
            "type: pipeline\ndisplay_name: demo-training\njobs:\n"
            "  prep:\n    type: command\n    component: ./components/prep/prep.yml\n"
            "  train:\n    type: command\n    component: azureml:demo_train@latest\n"
            "settings:\n  default_compute: azureml:cpu\n")
        rows = o.scan(root)
    assert [(r[1], r[2], r[5]) for r in rows] == [("demo-training", "prep", "demo_prep"), ("demo-training", "train", "demo_train")]


def test_azure_ml_live_job_export_names_steps_from_the_component_list():
    job = {"name": "run_1", "type": "pipeline", "display_name": "demo-training",
           "jobs": {"prep": {"component": "azureml:azureml_anonymous:1"}, "train": {"component": "azureml:azureml_anonymous:2"}}}
    comps = [{"name": "demo_prep", "id": "/x/components/demo_prep", "creation_context": {}},
             {"name": "demo_train", "id": "/x/components/demo_train", "creation_context": {}}]
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "job.json").write_text(json.dumps([job, dict(job, name="run_2")]))
        (Path(d) / "component.json").write_text(json.dumps(comps))
        rows = o.scan(d)
    assert [(r[1], r[2], r[5]) for r in rows] == [("demo-training", "prep", "demo_prep"), ("demo-training", "train", "demo_train")]
