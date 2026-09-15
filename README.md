# velox-skills

Claude Code plugin marketplace maintained by Velox.

## Install

```
/plugin marketplace add hieunle/velox-skills
/plugin install databricks-discovery
```

Update later with `/plugin marketplace update velox-skills`.

## Plugins

### `databricks-discovery`

A skill pack that covers the **discovery & assessment** phase of a data project on Databricks,
written for engineers who also own requirements. Databricks ships 29 official agent skills — all
for implementation; none for discovery, assessment, or requirements. This pack fills that gap by
encoding the methodology Databricks and its partners already publish (five-phase migration,
Lakebridge, SAT, UCX, Well-Architected Framework) into agent behaviour.

| Skill | Role |
|---|---|
| `discovery-intake` | Mandatory entry point. Three-axis intake (project type via the real driver · inputs available · decision to serve), source request per project type, evidence-sufficiency gate, blocking questions, hand-off. Seven project-type modules: migration, greenfield, consolidation, cost & performance, streaming, ML/AI, data sharing. |
| `requirements-extraction` | Documents, transcripts, tickets → `requirements.jsonl` with locators, stated-vs-inferred, conflicts, open questions. |
| `legacy-etl-archaeology` | Stored procedures, SSIS/Informatica, schedulers, SSRS → business-rule register (VERIFIED / CONFLICT / CODE-ONLY / CONFIG-ONLY / DEAD), dependency graph, inventory with real usage. Works alongside Lakebridge Analyzer and the `legacy-spec-extraction` skill. |
| `assessment-synthesis` | Registers → rationalization matrix (migrate / modernize / retire / defer), waves and pilot, estimate drivers, target-architecture outline, and an assessment report generated from the registers (`scripts/build_report.py`). |

Design principles the pack enforces: never invent object names or numbers; every statement carries
a locator and a `stated`/`inferred` label; the agent proposes into `runs/` and a human merges into
`registers/`; deliver what is possible while asking at most 3–5 blocking questions; the report is a
decision instrument with an evidence-sufficiency appendix.

Skills are written in English. Artifacts are produced in the user's working language.

## Repository layout

```
velox-skills/
├── .claude-plugin/marketplace.json
└── databricks-discovery/
    ├── .claude-plugin/plugin.json
    ├── skills/<skill>/SKILL.md (+ references/, scripts/)
    └── evals/
        ├── evals.json                    # test prompts + assertions
        └── fixtures/minhphat-migration/  # synthetic legacy SQL Server DW with graded traps
```
