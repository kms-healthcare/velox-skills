# ML estates — Azure ML workspaces, and what the inventory must hold before a move

A DW migration moves tables and the code that fills them. An ML estate adds a third thing that is
neither: the **model** — trained by a pipeline, registered with a version, read by an endpoint.
The inventory records all three or the move loses one of them. Read this alongside
`dw-artifact-guide.md` when the estate has an Azure ML workspace; the project-type module is
`project-type-ml-ai.md` when the project *is* ML, `project-type-migration.md` when ML is a
workstream of a platform move.

## 1. Listing the workspace — CLI v2

`az extension add -n ml`, then with `-w <workspace> -g <resource-group>`:

| Command | Inventory record | Notes |
|---|---|---|
| `az ml schedule list` | `pipeline`, with `schedule` from `trigger` (cron / recurrence, **time zone**) | The scheduled pipeline jobs: the real DAG. `is_enabled: false` → candidate `DEAD` |
| the pipeline YAML / SDK code in Git (`jobs:` with `component:` or `command:`, `inputs:` / `outputs:`) | `pipeline` and one `job` per step | `azureml:<data asset>` inputs are read edges; outputs registered as data assets or models are write edges |
| `az ml component list` | `job` (a registered, reusable step) | The code behind it is where the rules are — §2 |
| `az ml model list` → `az ml model show -n <name> -v <version>` | `model` | `properties` / `tags` usually name the training job → its writer edge; `path` is where the artefact sits |
| `az ml online-endpoint list` → `az ml online-deployment list --endpoint-name <e>` | `api_endpoint`, reading the `model` | `instance_type` × `instance_count` and `traffic` split: an always-on GPU for a 9-to-5 tool is a cost finding |
| `az ml batch-endpoint list` → `az ml batch-deployment list --endpoint-name <e>` | `job` (scoring), writing a `file_dataset` | `output_file_name` / the output datastore path |
| `az ml data list` → `az ml data show` | `file_dataset` (`uri_file`, `uri_folder`, `mltable`) | `path` names the datastore and the folder: that is the data the move reaches |
| `az ml datastore list` | `object_store` (ADLS / Blob container) | Names only — `credentials` are never copied; `write_records.py` refuses a record that carries one |
| `az ml compute list` | not inventory — a finding when a compute instance is never stopped, a cluster has `min_instances > 0` | `az ml compute show` for the idle shutdown |
| `az ml environment list` | not inventory — findings: unpinned `conda` dependencies, a custom Docker image nobody can rebuild, a CUDA pin | Migration cost drivers |
| `az ml job list --max-results 500` (filter by `experiment_name`, `creation_context.created_at`) | usage: the last job per pipeline / schedule → `last_write_at` | 90-day window, as for any usage claim |

**SDK v1 remnants** (`azureml.core`: `Experiment.submit`, `PipelineData`, `PythonScriptStep`,
`AutoMLConfig`; Designer drag-and-drop pipelines): the v2 CLI lists them partially or not at all.
Ask for the studio's Pipelines and Experiments pages exported, or the v1 scripts from Git. A
Designer pipeline has no code to convert: disposition `rewrite`, say so in the inventory.

## 2. Where the rules hide

- **Data preparation steps**: filters that define the population (`WHERE churned IS NULL`,
  `date >= '2019-01-01'`), the **label definition** (`churn = no order in 90 days`) — a business
  rule nobody wrote down, imputation defaults, outlier caps, the join that drops unmatched rows.
  Extract them as `business_rules` exactly as for a stored procedure; the anchor is the function
  name + content hash.
- **`MLTable` definitions** (`mltable.yml`: `transformations:` — `read_delimited`,
  `filter`, `convert_column_types`): rules in YAML, read by every job that mounts the asset.
- **Scoring scripts** (`score.py`: `init()` / `run()`): preprocessing re-implemented by hand —
  compare with the training step and record every difference as a `CONFLICT` (training/serving
  skew); decision thresholds (`proba > 0.37`); post-processing that maps scores to actions.
- **AutoML** jobs: `featurization` settings and the chosen `primary_metric` — the model's
  definition of "good".
- **Schedules**: cron strings with `time_zone`; a pipeline that runs on the 1st at 02:00 is a
  month-end job (the month-end trap applies).
- **Monitors / drift baselines**, where configured: the reference dataset is a data asset to
  inventory.

## 3. Findings this estate routinely yields

A model with no evaluation dataset and no recorded metric · an endpoint with no traffic in 90
days (`AmlOnlineEndpointTrafficLog` through the diagnostic settings; without it, `orphan: null`
and a question) · a registered model whose training data asset no longer exists · secrets in
`score.py` or in the environment variables of a deployment · v1 SDK code (retired) · a compute
instance running since its creation · a model trained on PII with no `holds_pii` on its data
assets.

## 4. What the move needs from the inventory

Each `model` record names its training `pipeline` (writer), its data assets (the pipeline's
readers), its endpoints (readers) and the owner who answers for the metric. On Databricks these
become an MLflow experiment, a Unity Catalog registered model (`catalog.schema.model`), Model
Serving and a Lakeflow job; the move itself is the ML team's — the inventory is the handover,
and a record missing from it is a model nobody moves.
