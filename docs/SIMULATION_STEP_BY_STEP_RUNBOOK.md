# Nexus V2 Simulation Step-by-Step Runbook

## Goal

Simulate the API Developer side and the DBA/Data Engineering handoff.

This shows:

```text
API Dumper reads ETL tables
API Dumper calls provider API
API Dumper writes JSONL gzip and manifest
API Dumper updates ETL control tables
S3/SQS can trigger the worker
DBA/Data Engineering continues from S3
```

## Part 1: Install database SQL

Run SQL files in order:

```bash
psql "$DATABASE_URL" -f sql/001_etl_control_tables.sql
psql "$DATABASE_URL" -f sql/002_indexes.sql
psql "$DATABASE_URL" -f sql/003_raw_staging_quarantine_tables.sql
psql "$DATABASE_URL" -f sql/005_delete_reconciliation_tables.sql
psql "$DATABASE_URL" -f sql/006_final_soft_delete_columns.sql
psql "$DATABASE_URL" -f sql/007_delete_reconciliation_procedure.sql
psql "$DATABASE_URL" -f sql/008_process_batch_with_delete_first_template.sql
psql "$DATABASE_URL" -f sql/009_security_hardening.sql
psql "$DATABASE_URL" -f sql/010_dynamic_entity_batch_rules.sql
psql "$DATABASE_URL" -f sql/011_dynamic_delete_reconciliation_template.sql
psql "$DATABASE_URL" -f sql/012_api_dumper_contract_and_simulation_support.sql
```

## Part 2: Seed API pull config

Example:

```sql
INSERT INTO etl.api_pull_config (
    source_system, brand_key, source_entity, api_endpoint,
    pull_frequency_minutes, overlap_minutes, safety_delay_minutes,
    enabled, default_run_type, s3_bucket, s3_prefix
)
VALUES (
    'Provider API', 'inplay', 'gameTx', '/records',
    5, 10, 5,
    true, 'createddate_snapshot', 'nexus-v2-raw-dev', 'raw'
)
ON CONFLICT (source_system, brand_key, source_entity)
DO UPDATE SET
    api_endpoint = EXCLUDED.api_endpoint,
    default_run_type = EXCLUDED.default_run_type,
    s3_bucket = EXCLUDED.s3_bucket,
    s3_prefix = EXCLUDED.s3_prefix,
    enabled = true,
    updated_at = now();
```

## Part 3: Start fake provider API

```bash
python scripts/simulation/fake_provider_api.py --port 8088
```

This starts a local provider API with 10 game transaction rows.

Check API manually:

```bash
curl 'http://127.0.0.1:8088/records?brand=inplay&entity=gameTx&date_field=createdDate&from=2026-05-11T10:00:00+08:00&to=2026-05-11T11:00:00+08:00&page=1&page_size=100'
```

Expected: 10 rows.

## Part 4: Run API Dumper simulator locally

This writes to a local folder that acts like S3.

```bash
python scripts/simulation/api_dumper_simulator.py \
  --dsn "$DATABASE_URL" \
  --source-system "Provider API" \
  --brand inplay \
  --entity gameTx \
  --api-base-url http://127.0.0.1:8088 \
  --s3-bucket nexus-v2-raw-dev \
  --s3-prefix raw \
  --local-s3-dir /tmp/nexus_s3 \
  --run-type createddate_snapshot \
  --window-from 2026-05-11T10:00:00+08:00 \
  --window-to 2026-05-11T11:00:00+08:00
```

Expected output:

```text
success = true
record_count = 10
batch_id = <uuid>
s3_key = raw/.../part-0001.jsonl.gz
manifest_s3_key = raw/.../manifest.json
```

Check database:

```sql
SELECT batch_id, run_type, status, api_record_count, s3_bucket, s3_key
FROM etl.batch_run
ORDER BY started_at DESC
LIMIT 5;
```

Expected:

```text
status = s3_written
api_record_count = 10
```

## Part 5: Simulate source-side delete

Delete one row from fake provider source:

```bash
curl -X POST 'http://127.0.0.1:8088/delete?externalId=TX010'
```

Check API again:

```bash
curl 'http://127.0.0.1:8088/records?brand=inplay&entity=gameTx&date_field=createdDate&from=2026-05-11T10:00:00+08:00&to=2026-05-11T11:00:00+08:00&page=1&page_size=100'
```

Expected: 9 rows.

## Part 6: Run API Dumper simulator again for same window

```bash
python scripts/simulation/api_dumper_simulator.py \
  --dsn "$DATABASE_URL" \
  --source-system "Provider API" \
  --brand inplay \
  --entity gameTx \
  --api-base-url http://127.0.0.1:8088 \
  --s3-bucket nexus-v2-raw-dev \
  --s3-prefix raw \
  --local-s3-dir /tmp/nexus_s3 \
  --run-type createddate_snapshot \
  --window-from 2026-05-11T10:00:00+08:00 \
  --window-to 2026-05-11T11:00:00+08:00
```

Expected:

```text
record_count = 9
```

This proves the API side can produce the new smaller snapshot.

The DBA/Data Engineering pipeline will later compare this 9-row snapshot with final active keys and mark the missing key as source-deleted.

## Part 7: Test real S3/SQS event plumbing

Prerequisites:

```text
S3 bucket exists
SQS queue exists
S3 ObjectCreated notification points to SQS
EC2/IAM role has S3/SQS permissions
```

Run:

```bash
python scripts/simulation/s3_sqs_poc_tester.py \
  --bucket nexus-v2-raw-dev \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/nexus-v2-s3-events \
  --region ap-southeast-1 \
  --brand inplay \
  --entity gameTx
```

Expected:

```text
SUCCESS: SQS received matching S3 event.
```

## Part 8: Troubleshooting

### Batch created but S3 key is null

```sql
SELECT batch_id, status, s3_bucket, s3_key, error_message
FROM etl.batch_run
ORDER BY started_at DESC
LIMIT 10;
```

If `s3_key` is null, API succeeded but file write probably failed.

### Watermark moved incorrectly

```sql
SELECT *
FROM etl.api_watermark
ORDER BY updated_at DESC;
```

Watermark should only move after successful S3 write.

### Source-delete did not happen

Check:

```sql
SELECT batch_id, run_type, is_complete_snapshot, pagination_complete, api_record_count
FROM etl.batch_run
ORDER BY started_at DESC
LIMIT 10;
```

For delete reconciliation, expected:

```text
run_type = createddate_snapshot
is_complete_snapshot = true
pagination_complete = true
```

### API failed

```sql
SELECT *
FROM etl.api_pull_run
WHERE status = 'failed'
ORDER BY started_at DESC;
```

### Backfill needed

```sql
SELECT *
FROM etl.api_backfill_request
WHERE status = 'pending'
ORDER BY priority ASC, requested_at ASC;
```

## Part 9: Reset fake provider API

```bash
curl -X POST 'http://127.0.0.1:8088/reset'
```

This restores the fake API source back to 10 rows.
