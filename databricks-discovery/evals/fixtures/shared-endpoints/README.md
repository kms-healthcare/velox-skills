# Fixture: shared-endpoints

A Databricks bundle with `dev` and `prod` targets whose jobs reach three external endpoints, for
testing that `legacy-etl-archaeology` resolves each endpoint per environment and tells wiring that
is a fact from wiring that carries risk (VEL-1687). Everything under `sources/` is what the agent
receives. `TRAPS.md` is for graders only. Run live by a model (eval 5 in `../../evals.json`); there
is no script grader.
