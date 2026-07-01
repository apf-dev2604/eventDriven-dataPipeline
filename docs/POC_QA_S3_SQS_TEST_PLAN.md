# POC QA Test Plan for S3, SQS, EC2 Worker, and Delete Reconciliation

## Goal

Prove that the pipeline works before production.

We want to prove:

1. S3 receives files.
2. S3 sends events to SQS.
3. EC2 worker receives SQS messages.
4. Worker loads raw data.
5. Adapter loads staging data.
6. Stored procedure performs delete-before-insert safely.
7. Delete history is written.
8. Final rows are soft-deleted.
9. SQS messages are deleted only after successful processing.
10. Failed messages retry and eventually go to DLQ.

## Test 1: S3 to SQS event

### Steps

1. Upload a small test file to the raw S3 bucket.
2. Use the exact expected prefix:

```text
raw/brand=inplay/entity=gameTx/run_type=createddate_snapshot/creation_date=2026-04-01/batch_id=<uuid>/part-0001.jsonl.gz
```

3. Check SQS queue message count.

### Expected result

SQS should show one available message.

### Pass condition

S3 upload creates an SQS message.

## Test 2: EC2 worker receives message

### Steps

1. Start `sqs-worker.service`.
2. Check logs:

```bash
sudo journalctl -u sqs-worker -f
```

3. Confirm worker receives the S3 bucket/key.

### Expected result

Worker logs show the S3 object path and batch ID.

### Pass condition

Worker can poll SQS and parse the S3 event.

## Test 3: Raw load

### Steps

1. Upload a JSONL gzip file with 3 records.
2. Let the worker process it.
3. Query raw tables:

```sql
SELECT * FROM raw.s3_files ORDER BY created_at DESC LIMIT 5;
SELECT count(*) FROM raw.api_events WHERE batch_id = '<batch_id>';
```

### Expected result

- 1 row in `raw.s3_files`.
- 3 rows in `raw.api_events`.

### Pass condition

Raw loading works and preserves evidence.

## Test 4: Staging and source key load

### Steps

1. Process the test batch.
2. Query:

```sql
SELECT count(*) FROM staging.game_tx WHERE batch_id = '<batch_id>';
SELECT count(*) FROM staging.source_batch_keys WHERE batch_id = '<batch_id>';
```

### Expected result

Staging row count and source key count match the source file count.

### Pass condition

Adapter maps data and writes keys.

## Test 5: Delete-before-insert scenario

### Setup

First batch contains 3 records:

```text
A, B, C
```

Second batch for the same scope contains 2 records:

```text
A, B
```

### Steps

1. Process first batch.
2. Confirm final has A, B, C active.
3. Process second complete snapshot batch.
4. Query delete history:

```sql
SELECT external_id, delete_reason
FROM final_history.gameTX_delete_history
WHERE batch_id = '<second_batch_id>';
```

5. Query final:

```sql
SELECT externalId, is_source_deleted
FROM final_consolidated.gameTX
WHERE externalId IN ('A','B','C');
```

### Expected result

- C exists in delete history.
- C is marked `is_source_deleted = true`.
- A and B remain active.

### Pass condition

Missing source row is safely replicated as source-deleted in final.

## Test 6: Reactivation

### Setup

Third batch contains:

```text
A, B, C
```

### Expected result

C is reactivated:

```text
is_source_deleted = false
source_deleted_at = null
```

## Test 7: Incomplete API batch must not delete

### Steps

1. Simulate failed pagination or set batch status to failed.
2. Process a file with fewer rows.
3. Confirm delete procedure skips delete detection.

### Expected result

No rows are marked deleted.

### Pass condition

Incomplete batch cannot cause false delete.

## Test 8: DLQ retry behavior

### Steps

1. Upload a malformed file.
2. Worker should fail processing.
3. Message should reappear after visibility timeout.
4. After max receive count, message moves to DLQ.

### Expected result

Failed message is not lost.

### Pass condition

Retry and DLQ mechanism works.

## POC acceptance checklist

- [ ] S3 event sends message to SQS.
- [ ] Worker reads SQS message.
- [ ] Worker loads raw data.
- [ ] Adapter loads staging and source keys.
- [ ] Snapshot batch can soft-delete missing final rows.
- [ ] Delete history contains old final row.
- [ ] Reactivation works.
- [ ] Failed batch does not delete.
- [ ] DLQ receives repeatedly failed messages.
- [ ] Logs show batch ID, S3 key, row counts, and status.
