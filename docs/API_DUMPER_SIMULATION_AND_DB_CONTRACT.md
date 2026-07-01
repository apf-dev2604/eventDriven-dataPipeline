# Nexus V2 API Dumper Simulation and Database Contract

## 1. Purpose

This document explains what the API Developer/Dumper should do, what database tables it should touch, and how to simulate the full API-to-S3-to-ETL handoff.

The goal is to make the API Dumper a small, clear component instead of one large unclear process.

Plain English:

```text
The API Dumper is the delivery driver.
It reads the delivery instruction, gets the package from the provider, writes the package to S3, and records the delivery ticket.
It does not open the warehouse shelves, final tables, staging tables, or delete history.
```

## 2. Responsibility boundary

### API Developer owns

```text
Provider API pull
ETL control table lookup
batch_run insert/update
api_pull_run insert/update
api_watermark update after success
S3 file write
API failure/gap/backfill logging
```

### DBA/Data Engineering owns

```text
S3 event processing
SQS worker
raw.s3_files
raw.api_events
staging tables
staging.source_batch_keys
delete reconciliation
delete_history
final soft delete
final upsert
quarantine
monitoring reports
```

The API Developer must not directly write to:

```text
raw.*
staging.*
final_consolidated.*
final_history.*
rejected.*
etl.source_delete_audit
```

## 3. API Dumper small process breakdown

### Process A: Read pull configuration

Program/script:

```text
api_dumper_simulator.py
```

Database lookup:

```sql
SELECT *
FROM etl.api_pull_config
WHERE enabled = true;
```

Purpose:

```text
Know which brand/entity/API endpoint should be pulled.
```

Troubleshooting:

```sql
SELECT source_system, brand_key, source_entity, enabled, api_endpoint, s3_bucket, s3_prefix
FROM etl.api_pull_config
ORDER BY brand_key, source_entity;
```

If `enabled = false`, the dumper should skip it.

---

### Process B: Read dynamic brand/entity rule

Database lookup:

```sql
SELECT *
FROM etl.entity_batch_rule
WHERE source_system = :source_system
  AND brand_key = :brand_key
  AND source_entity = :source_entity
  AND enabled = true;
```

Purpose:

```text
Know which date field to use for this brand/entity.
Example: createdDate, settledDate, transactionDate, updatedAt.
```

Why this matters:

```text
createdDate is only one example. Other brands/entities may use a different date parameter.
```

---

### Process C: Read or create watermark

Database lookup:

```sql
SELECT *
FROM etl.api_watermark
WHERE source_system = :source_system
  AND brand_key = :brand_key
  AND source_entity = :source_entity;
```

If missing:

```sql
INSERT INTO etl.api_watermark (source_system, brand_key, source_entity)
VALUES (:source_system, :brand_key, :source_entity)
ON CONFLICT (source_system, brand_key, source_entity) DO NOTHING;
```

Purpose:

```text
Know where the last successful API pull stopped.
```

Important:

```text
Do not update the watermark until API pull and S3 write both succeed.
```

---

### Process D: Compute API window

Example:

```text
last_successful_to = 10:25
overlap_minutes = 10
safety_delay_minutes = 5
current time = 10:35

request_from = 10:15
request_to   = 10:30
```

Plain English:

```text
The overlap catches late records.
The safety delay avoids pulling data that is still being written by the source.
```

---

### Process E: Create batch_run and api_pull_run

Insert batch:

```sql
INSERT INTO etl.batch_run (
    source_system, brand_key, source_entity, run_type,
    requested_from, requested_to, status,
    external_batch_id, date_field,
    is_complete_snapshot, pagination_complete
)
VALUES (
    :source_system, :brand_key, :source_entity, :run_type,
    :requested_from, :requested_to, 'created',
    :external_batch_id, :date_field,
    :is_complete_snapshot, false
)
RETURNING batch_id;
```

Insert API attempt:

```sql
INSERT INTO etl.api_pull_run (
    batch_id, source_system, brand_key, source_entity,
    run_type, requested_from, requested_to, status
)
VALUES (
    :batch_id, :source_system, :brand_key, :source_entity,
    :run_type, :requested_from, :requested_to, 'started'
);
```

Purpose:

```text
Create a traceable ticket before calling the provider API.
```

---

### Process F: Call provider API

Sample API call:

```text
GET /records?brand=inplay&entity=gameTx&date_field=createdDate&from=2026-05-11T10:00:00+08:00&to=2026-05-11T11:00:00+08:00&page=1&page_size=100
```

Before calling:

```sql
UPDATE etl.batch_run
SET status = 'pulling'
WHERE batch_id = :batch_id;

UPDATE etl.api_pull_run
SET status = 'api_calling'
WHERE batch_id = :batch_id;
```

After API success:

```sql
UPDATE etl.api_pull_run
SET status = 'api_success',
    api_record_count = :api_record_count
WHERE batch_id = :batch_id;
```

Production rule:

```text
If pagination fails, timeout happens, or API result is incomplete, mark the batch failed.
Do not write it as a complete snapshot.
Do not update watermark.
```

---

### Process G: Write JSONL gzip file and manifest to S3

Data file format:

```text
1 JSON record per line
gzip compressed
UTF-8
```

S3 key example:

```text
raw/source_system=provider_api/brand=inplay/entity=gameTx/run_type=createddate_snapshot/date_field=createdDate/window_from=20260511T100000+0800/window_to=20260511T110000+0800/batch_id=<uuid>/part-0001.jsonl.gz
```

Manifest key:

```text
same folder/manifest.json
```

Manifest example:

```json
{
  "source_system": "Provider API",
  "brand_key": "inplay",
  "source_entity": "gameTx",
  "run_type": "createddate_snapshot",
  "date_field": "createdDate",
  "window_from": "2026-05-11T10:00:00+08:00",
  "window_to": "2026-05-11T11:00:00+08:00",
  "record_count": 9,
  "api_success": true,
  "pagination_complete": true,
  "is_complete_snapshot": true,
  "external_batch_id": "api-inplay-gameTx-001",
  "internal_batch_id": "<uuid>",
  "checksum_sha256": "..."
}
```

---

### Process H: Mark S3 written

After successful S3 write:

```sql
UPDATE etl.batch_run
SET status = 's3_written',
    s3_bucket = :s3_bucket,
    s3_key = :s3_key,
    manifest_s3_bucket = :s3_bucket,
    manifest_s3_key = :manifest_s3_key,
    manifest_payload = :manifest_json::jsonb,
    api_record_count = :api_record_count,
    pagination_complete = :pagination_complete
WHERE batch_id = :batch_id;
```

Update API pull run:

```sql
UPDATE etl.api_pull_run
SET status = 'completed',
    api_record_count = :api_record_count,
    s3_bucket = :s3_bucket,
    s3_key = :s3_key,
    completed_at = now()
WHERE batch_id = :batch_id;
```

---

### Process I: Update watermark

Only after API and S3 success:

```sql
INSERT INTO etl.api_watermark (
    source_system, brand_key, source_entity,
    last_successful_from, last_successful_to,
    last_batch_id, last_s3_bucket, last_s3_key, updated_at
)
VALUES (
    :source_system, :brand_key, :source_entity,
    :requested_from, :requested_to,
    :batch_id, :s3_bucket, :s3_key, now()
)
ON CONFLICT (source_system, brand_key, source_entity)
DO UPDATE SET
    last_successful_from = EXCLUDED.last_successful_from,
    last_successful_to = EXCLUDED.last_successful_to,
    last_batch_id = EXCLUDED.last_batch_id,
    last_s3_bucket = EXCLUDED.last_s3_bucket,
    last_s3_key = EXCLUDED.last_s3_key,
    updated_at = now();
```

Do not update watermark on failed runs.

---

### Process J: Failure handling

If API/S3 fails:

```sql
UPDATE etl.batch_run
SET status = 'failed',
    error_message = :error_message,
    completed_at = now()
WHERE batch_id = :batch_id;

UPDATE etl.api_pull_run
SET status = 'failed',
    error_message = :error_message,
    completed_at = now()
WHERE batch_id = :batch_id;
```

Log gap:

```sql
INSERT INTO etl.api_gap_log (
    source_system, brand_key, source_entity,
    gap_from, gap_to, reason_code, severity,
    related_batch_id, details
)
VALUES (
    :source_system, :brand_key, :source_entity,
    :requested_from, :requested_to,
    'api_dumper_failed', 'critical',
    :batch_id,
    jsonb_build_object('error_message', :error_message)
);
```

Create backfill request:

```sql
INSERT INTO etl.api_backfill_request (
    source_system, brand_key, source_entity,
    backfill_from, backfill_to, priority,
    reason, batch_id, error_message
)
VALUES (
    :source_system, :brand_key, :source_entity,
    :requested_from, :requested_to, 10,
    'API Dumper failed; needs rerun', :batch_id, :error_message
);
```

## 4. Source-delete simulation

### Starting state

Fake API source has 10 records:

```text
TX001 TX002 TX003 TX004 TX005 TX006 TX007 TX008 TX009 TX010
```

### Run 1

API Dumper pulls snapshot and writes 10 records to S3.

### Simulate source-side delete

Call fake API:

```bash
curl -X POST 'http://127.0.0.1:8088/delete?externalId=TX010'
```

Now provider source has 9 records.

### Run 2

API Dumper pulls the same snapshot window and writes 9 records to S3.

DBA/Data Engineering pipeline then detects:

```text
TX010 exists in final but no longer exists in staging.source_batch_keys for this complete snapshot batch.
```

Expected ETL action:

```text
TX010 copied to final_history.gameTX_delete_history
TX010 marked is_source_deleted = true in final
```

## 5. Troubleshooting queries

### Latest batches

```sql
SELECT batch_id, brand_key, source_entity, run_type, requested_from, requested_to,
       status, api_record_count, raw_record_count, staging_record_count,
       final_insert_count, final_update_count, quarantine_count, error_message
FROM etl.batch_run
ORDER BY started_at DESC
LIMIT 20;
```

### API pull failures

```sql
SELECT *
FROM etl.api_pull_run
WHERE status = 'failed'
ORDER BY started_at DESC;
```

### Watermark check

```sql
SELECT *
FROM etl.api_watermark
ORDER BY updated_at DESC;
```

### Gap check

```sql
SELECT *
FROM etl.api_gap_log
WHERE resolved_at IS NULL
ORDER BY detected_at DESC;
```

### Pending backfills

```sql
SELECT *
FROM etl.api_backfill_request
WHERE status = 'pending'
ORDER BY priority ASC, requested_at ASC;
```

### Delete audit

```sql
SELECT *
FROM etl.source_delete_audit
ORDER BY started_at DESC
LIMIT 20;
```

### Delete history

```sql
SELECT batch_id, brand_key, platform, external_id, creation_date, settled_date,
       delete_reason, deleted_detected_at
FROM final_history.gameTX_delete_history
ORDER BY deleted_detected_at DESC
LIMIT 20;
```

## 6. Recommended API Developer permissions

Create a dedicated database role, for example:

```text
nexus_dumper
```

Allowed:

```text
SELECT on etl.api_pull_config
SELECT on etl.entity_batch_rule
SELECT on etl.v_api_dumper_worklist
SELECT/INSERT/UPDATE on etl.api_watermark
SELECT/INSERT/UPDATE on etl.batch_run
SELECT/INSERT/UPDATE on etl.api_pull_run
INSERT/SELECT/UPDATE on etl.api_gap_log
INSERT/SELECT/UPDATE on etl.api_backfill_request
SELECT/UPDATE on etl.reconciliation_scope
```

Not allowed:

```text
raw.*
staging.*
final_consolidated.*
final_history.*
rejected.*
```

## 7. Files added for simulation

```text
scripts/simulation/fake_provider_api.py
scripts/simulation/api_dumper_simulator.py
scripts/simulation/s3_sqs_poc_tester.py
sql/012_api_dumper_contract_and_simulation_support.sql
```
