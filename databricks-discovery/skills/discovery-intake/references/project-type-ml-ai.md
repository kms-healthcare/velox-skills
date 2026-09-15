# Project type 6 — ML / AI platform

Load when Axis A = ML / AI. Most "AI projects" discovered here are data projects wearing an AI
costume: the model or the agent is blocked because the Silver/Gold data does not exist or is not
trusted. The assessment must be willing to say that.

## Recognising it

Signals: "models stuck in notebooks", "we can't get to production", "GenAI on our data", "RAG",
"chatbot over our documents", "agents", "MLOps", "feature store", "the data scientists each have
their own copy".

## The real driver

> "Which decision or task will the model / agent take over, from whom, and how will you know it is
> right?"

If nobody can name the ground truth or the evaluation, there is no ML project yet.

## Decisions this assessment serves

Build vs buy per use case (Agent Bricks / Genie vs Agent Framework custom); data readiness and what
must be built first; governance model for models, prompts, and PII; MLOps maturity target;
inference cost envelope.

## Sources to request

### Required

| Source | Why | How |
|---|---|---|
| **Use case list with the decision, current owner, and success metric** | Separates real use cases from demos | Workshop |
| **Ground-truth / evaluation data** per use case, or an honest "none" | Without it no quality claim can be made | Data science team |
| **Inventory of existing models, notebooks, endpoints**, how each is deployed and monitored today | MLOps baseline | MLflow if used; otherwise notebook export |
| **Feature / training data sources** with freshness, owner, and whether they exist in Silver/Gold | Data readiness | UC inventory; interviews |
| **PII and regulatory constraints on inputs and outputs** | Prompt/PII leakage, model risk | Legal / DPO |
| **Document corpus inventory** (for RAG): sources, volume, access control, update frequency | Knowledge Assistant feasibility | Document owners |

### Recommended

Latency and cost tolerance per use case; who approves a model change; existing evaluation results;
user population for AI tools.

## Databricks tools to use instead of building

| Need | Use |
|---|---|
| Chat over documents | **Agent Bricks Knowledge Assistant** (GA) — try before building RAG |
| Structured extraction from documents | **Agent Bricks Document Intelligence / Information Extraction** (GA) |
| NL over tables | **Genie Agents** on curated data + metric views |
| Multi-agent orchestration | **Agent Bricks Supervisor** (GA) |
| Custom agents | **Mosaic AI Agent Framework** + **MLflow 3** tracing/evaluation + **Model Serving** |
| Guardrails, logging, PII detection on LLM calls | **Mosaic AI Gateway** |
| Retrieval | **AI Search** (ex-Vector Search) |
| Drift and quality over time | **Data Quality Monitoring** (ex-Lakehouse Monitoring) inference tables |

## Conclusions the report must reach

1. **Use case → build/buy mapping** with the Databricks product that covers it, and what remains custom.
2. **Data readiness per use case** — which Silver/Gold tables exist, which must be built first.
   Often this becomes a greenfield or migration scope.
3. **Evaluation readiness** — ground truth exists / must be created / cannot exist.
4. **Governance gaps**: model registry, approval, PII in prompts and outputs, audit.
5. **MLOps maturity** and the target.
6. **Cost envelope**: inference volume × latency tier.

## Evidence-sufficiency rules

| Cannot claim | Without |
|---|---|
| "The model / agent will be accurate enough" | An evaluation set and a baseline |
| "Data is ready" | The Gold tables named and profiled |
| "RAG is feasible" | Corpus inventory with access control mapped |
| "Cost is X" | Expected call volume from a named consumer |

## Confirmation questions

- "What does a correct answer look like, and who decides?"
- "Which columns / documents must never reach a prompt?"
- "If the model is wrong, who is accountable and what is the fallback?"
- "Is the data this needs already in Silver/Gold, or are we building that first?"

## What is routinely missed

No evaluation set; data not ready; PII in prompts; inference cost of always-on GPU endpoints; no
owner for model decisions; fine-tuning proposed where retrieval suffices.

## Cost-risk flags

Fine-tuning before trying RAG / Agent Bricks; provisioned GPU endpoints for a 9-to-5 internal tool;
building a custom agent for a task Genie already does.
