# ETL Blueprint 

This package contains the updated production design for ETL pipeline with:

- dynamic brand/entity date rules,
- 5-minute current pulls,
- rolling 3-day lookback windows,
- source-delete replication,
- delete-before-insert workflow,
- delete history logging,
- soft-delete final table behavior,
- S3 + SQS + EC2 worker POC QA,
- IAM/deployment request checklist,
- CDC/replication integration notes,
- production timeline and Gantt chart.

## Main workflow

```text
API Dumper
→ S3 raw JSONL gzip
→ S3 ObjectCreated event
→ SQS
→ EC2 sqs_worker.py
→ pipeline_runner.py
→ raw_loader.py
→ raw tables
→ adapter
→ staging tables + staging.source_batch_keys
→ etl.process_batch(batch_id)
    → validate complete dynamic snapshot batch
    → write missing final rows to delete history
    → soft-delete missing final rows
    → upsert current staging rows
→ final/history/quarantine/audit
```

## New files to read first

1. `docs/STEP_BY_STEP_NON_TECHNICAL_EXPLANATION.md`
2. `docs/DEPLOYMENT_REQUEST_IAM_PERMISSIONS.md`
3. `docs/POC_QA_S3_SQS_TEST_PLAN.md`
4. `docs/PROJECT_TIMELINE_GANTT.md`
5. `docs/CDC_REPLICATION_INTEGRATION.md`
6. `security/HARDCORE_SECURITY_CHECKLIST.md`

## New SQL files

Run after the previous SQL files:

```bash
psql "$DATABASE_URL" -f sql/010_dynamic_entity_batch_rules.sql
psql "$DATABASE_URL" -f sql/011_dynamic_delete_reconciliation_template.sql
```

## Production answer on timeline

- POC: 2 to 3 weeks.
- Hardened UAT-ready version: 4 to 6 weeks.
- Production-ready without CDC: 8 to 12 weeks.
- Production-ready with CDC/replication: 10 to 16 weeks.

The CDC timeline is longer because it requires replication permissions, source database configuration, security review, and duplicate/delete handling rules.

## V4 simulation additions

This package now includes API Dumper simulation scripts and a clearer database contract for the API Developer.

New files:

```text
sql/012_api_dumper_contract_and_simulation_support.sql
scripts/simulation/fake_provider_api.py
scripts/simulation/api_dumper_simulator.py
scripts/simulation/s3_sqs_poc_tester.py
docs/API_DUMPER_SIMULATION_AND_DB_CONTRACT.md
docs/SIMULATION_STEP_BY_STEP_RUNBOOK.md
```

### What the simulation proves

```text
API Developer can read ETL config/rules/watermark.
API Developer can create batch_run and api_pull_run.
API Developer can call a sample provider API.
API Developer can write JSONL gzip and manifest files.
API Developer can update batch status and watermark correctly.
API failure can create gap/backfill records.
Source-side delete can be simulated by returning 10 rows first, then 9 rows for the same snapshot scope.
```

### Important API Developer boundary

The API Developer may write only to ETL control tables:

```text
etl.api_watermark
etl.batch_run
etl.api_pull_run
etl.api_gap_log
etl.api_backfill_request
```

The API Developer should not write to:

```text
raw.*
staging.*
final_consolidated.*
final_history.*
rejected.*
```

Read these for the simulation:

```text
docs/API_DUMPER_SIMULATION_AND_DB_CONTRACT.md
docs/SIMULATION_STEP_BY_STEP_RUNBOOK.md
```
