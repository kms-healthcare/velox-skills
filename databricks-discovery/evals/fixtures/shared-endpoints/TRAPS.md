# Deliberate traps in this fixture — grader reference. Do not give to the agent under test.

Deploy: `.github/workflows/deploy.yml:14` runs `databricks bundle deploy -t dev|prod` and passes no
`--var` / `BUNDLE_VAR_*`, so each value is the bundle default unless the target overrides it.

1. **Shared, destructive, guarded → FINDING.** `orders` on `kafka-prod.acme.internal:9092`, group
   `orders-loader`: neither target overrides `kafka_bootstrap` / `orders_topic` / `orders_group`
   (`databricks.yml:8,10,12`), so dev resolves to the production topic and the production consumer
   group, and `consume_orders.py:17` commits offsets — a dev run takes partitions and messages from
   production. Guard: dev sets `orders_consumer_enabled: "false"` (`databricks.yml:28`), read at
   `consume_orders.py:8`. It is a variable anyone can flip (`--var`, one YAML line), so the remaining
   risk stays real: severity medium or above, `detail` names the guard and both locators. Recording
   it only as a source system / fact is the miss Addepto reported.
2. **Shared, read-only → FACT, no finding.** `fx_api_url` = `https://fx.acme.com/v2` in both
   targets (`databricks.yml:20`, no override); `fx_rates.py:8` only GETs. A source system with its
   per-environment target; no finding for the sharing.
3. **Separate per environment → no finding (must-not-flag).** `returns`: dev overrides to
   `kafka-dev.acme.internal:9092` / `returns-dev` (`databricks.yml:29-30`); prod keeps
   `kafka-prod…` / `returns`. It commits (`consume_returns.py:13`) and has no guard, and that is
   fine — nothing is shared. Reading the default as dev's value would invent a shared-resource
   finding here.
4. Databricks tables (`bronze.orders`, `bronze.returns`, `silver.fx_rates`) live in a separate
   workspace per target (`databricks.yml:26,33`) — not a shared resource.
