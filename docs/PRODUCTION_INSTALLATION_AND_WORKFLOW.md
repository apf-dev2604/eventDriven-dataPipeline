# Nexus V2 Production Installation, Deployment, Security, and Workflow

## Purpose

This package updates Nexus V2 so source-side deletes can be replicated safely. The design uses complete createdDate snapshot batches to detect missing source records. Missing records are written to delete history first, then soft-deleted from final.

## Main workflow

```text
API Dumper
-> S3 raw JSONL gzip file
-> S3 ObjectCreated event
-> SQS queue
-> EC2 sqs_worker.py
-> pipeline_runner.py
-> raw_loader.py
-> raw.s3_files + raw.api_events
-> provider adapter
-> staging tables
-> etl.process_batch(batch_id)
   -> source-delete reconciliation first
   -> final upsert second
   -> history/quarantine/audit
-> delete SQS message only after success
```

## Where deletion fits

Delete reconciliation happens after staging is loaded and before final upsert.

```text
staging.game_tx loaded
-> validate batch is complete
-> compare active final keys against current staging keys
-> copy missing final rows to final_history.gameTX_delete_history
-> mark missing final rows is_source_deleted=true
-> upsert current staging rows into final
```

## Installation order

```bash
psql "$DATABASE_URL" -f sql/001_etl_control_tables.sql
psql "$DATABASE_URL" -f sql/002_indexes.sql
psql "$DATABASE_URL" -f sql/003_raw_staging_quarantine_tables.sql
psql "$DATABASE_URL" -f sql/005_delete_reconciliation_tables.sql
psql "$DATABASE_URL" -f sql/006_final_soft_delete_columns.sql
psql "$DATABASE_URL" -f sql/007_delete_reconciliation_procedure.sql
psql "$DATABASE_URL" -f sql/008_process_batch_with_delete_first_template.sql
psql "$DATABASE_URL" -f sql/009_security_hardening.sql
```

## API Dumper mechanism

Every 5 minutes, the dumper should pull the current window and also read `etl.reconciliation_scope` for due rolling 3-day createdDate snapshot windows. Snapshot batches must fetch the complete current source result for that createdDate scope and save it to S3 before any watermark or batch success is recorded.

## Safety rule

Only `run_type = createddate_snapshot` or `manual_replay_snapshot` can mark source deletes. Partial incremental batches must not mark deletes.

## Delete example

Yesterday, final has 10 records for `creationDate = 2026-04-01`. Today, the provider returns 9 records for the same createdDate snapshot. The missing externalId is copied to `final_history.gameTX_delete_history`, then marked `is_source_deleted = true` in `final_consolidated.gameTX`. The row is not hard-deleted.

## Security baseline

No AWS keys in code. EC2 uses IAM instance profile. S3 blocks public access and uses KMS encryption. SQS policy allows only the raw S3 bucket to send events. PostgreSQL application users are not superusers. TLS is required for PostgreSQL. Use Secrets Manager or SSM Parameter Store for secrets.
