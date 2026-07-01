# API Dumper Developer Requirements

## Required tables

- `etl.api_pull_config`: what sources/entities are enabled and how to pull them.
- `etl.api_watermark`: last successful current window.
- `etl.reconciliation_scope`: rolling 3-day createdDate snapshot/lookback scopes.
- `etl.batch_run`: one row per batch.
- `etl.api_pull_run`: one row per API attempt.

## Required run types

- `incremental_current`: current 5-minute insert/update, no delete detection unless complete.
- `createddate_snapshot`: full current source result for a createdDate scope, allowed for delete detection.
- `manual_replay_snapshot`: manually requested replay snapshot, allowed for delete detection.

## Required source API behavior for delete safety

For `createddate_snapshot`, the developer must guarantee all pages are fetched, zero rows is different from API failure, failed API does not produce a successful batch, S3 write succeeds before batch is marked written, and only complete snapshots are compared for deletes.

## Required logs per run

source_system, brand_key, source_entity, run_type, requested_from, requested_to, page_count, api_record_count, full_pagination_completed flag, s3_bucket, s3_key, batch_id, start/end time, and error message.
