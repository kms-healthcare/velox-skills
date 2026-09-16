# velox-skills

Claude Code plugin marketplace maintained by Velox.

## Install

```
/plugin marketplace add kms-healthcare/velox-skills
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
| `assessment-synthesis` | Registers → rationalization matrix (migrate / modernize / retire / defer), waves and pilot, estimate drivers, target-architecture outline. The client deliverables — an Excel workbook plus the assessment report in Markdown and `.docx` — are generated from the registers by `scripts/build_deliverables.py`; only four prose sections are hand-written. |

Design principles the pack enforces: never invent object names or numbers; every statement carries
a locator and a `stated`/`inferred` label; the agent proposes into `runs/` and a human merges into
`registers/`; deliver what is possible while asking at most five blocking questions per turn; the
report is a decision instrument with an evidence-sufficiency appendix.

Output is budgeted, because an assessment that describes everything decides nothing. Evidence
excerpts, finding details and requirement statements have character limits; the four hand-written
report sections have word budgets the generator warns about; the chat reply is capped because the
report and the workbook are the deliverables. Exactly one report is produced, and it is generated.

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
        ├── trigger/                      # queries for description-triggering evals
        └── fixtures/minhphat-migration/  # synthetic legacy SQL Server DW with graded traps
```
