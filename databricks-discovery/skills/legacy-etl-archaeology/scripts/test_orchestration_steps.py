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
    # one row per step, carrying both locators — not one per source
    assert rows == [
        ("pipeline", "PL_A", "Run", "calls", "pipeline", "PL_Child", "", "git/pipeline/PL_A.json; live/pipeline.json[0]"),
        ("pipeline", "PL_A", "Log", "calls", "procedure", "ctl.usp_Log", "", "git/pipeline/PL_A.json; live/pipeline.json[0]"),
    ]


def test_watermark_lookup_copy_sink_azure_ml_and_databricks_steps_are_edges():
    acts = [
        {"name": "WM", "type": "Lookup", "typeProperties": {"source": {"sqlReaderStoredProcedureName": "ctl.usp_GetWatermark"}}},
        {"name": "Load", "type": "Copy", "typeProperties": {"sink": {"sqlWriterStoredProcedureName": "stg.usp_Upsert"}}},
        {"name": "ML", "type": "AzureMLExecutePipeline", "mlPipelineId": "pipe-1"},
        {"name": "DBX", "type": "DatabricksNotebook", "typeProperties": {"notebookPath": "/Shared/clean"}},
    ]
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "p.json").write_text(json.dumps([{"name": "PL", "activities": acts}]))
        assert [(r[2], r[4], r[5]) for r in o.scan(d)] == [
            ("WM", "procedure", "ctl.usp_GetWatermark"), ("Load", "procedure", "stg.usp_Upsert"),
            ("ML", "pipeline", "pipe-1"), ("DBX", "notebook", "/Shared/clean")]


def test_bracketed_names_join_and_expressions_stay_unresolved():
    acts = [dict(LOG, storedProcedureName="[ctl].[usp_Log]"),
            dict(LOG, name="Dyn", storedProcedureName={"value": "@item().proc", "type": "Expression"})]
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "p.json").write_text(json.dumps([{"name": "PL", "activities": acts}]))
        assert [(r[5], r[6]) for r in o.scan(d)] == [("ctl.usp_Log", ""), ("", "@item().proc")]


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


def test_azure_ml_step_matching_two_components_is_flagged_not_guessed():
    job = {"name": "r", "type": "pipeline", "jobs": {"prep": {"component": "azureml:azureml_anonymous:1"}}}
    comps = [{"name": n, "id": "/x/components/" + n, "creation_context": {}} for n in ("a_prep", "b_prep")]
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "job.json").write_text(json.dumps([dict(job, display_name="A"), dict(job, name="r2", display_name="B")]))
        (Path(d) / "component.json").write_text(json.dumps(comps))
        rows = o.scan(d)
    assert [(r[1], r[5], r[6]) for r in rows] == [("A", "prep", "ambiguous: a_prep | b_prep"), ("B", "prep", "ambiguous: a_prep | b_prep")]
