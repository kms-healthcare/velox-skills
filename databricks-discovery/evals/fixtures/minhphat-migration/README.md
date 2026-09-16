# Fixture: minhphat-migration

Synthetic legacy SQL Server DW for testing the databricks-discovery skill pack on a migration-type
project. Everything under `sources/` is what the agent receives. `TRAPS.md` is for graders only.

Test prompt (English, as an engineer would type it):

> Minh Phat Retail wants to move their SQL Server data warehouse to Databricks. I have a sources/
> folder with DDL, stored procedures, one SSIS package, one SSRS report, SQL Agent exports, Query
> Store output, SSRS logs, row counts, a 2016 spec, kickoff notes and one DBA interview transcript.
> Help me run discovery & assessment: identify the project type, check whether the inputs are
> sufficient, extract requirements and business rules, and give me a draft assessment with the list
> of questions to ask the client.
