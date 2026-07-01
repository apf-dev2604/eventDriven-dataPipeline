CREATE INDEX IF NOT EXISTS ix_api_pull_config_enabled ON etl.api_pull_config (enabled, source_system, brand_key, source_entity);
CREATE INDEX IF NOT EXISTS ix_api_watermark_key ON etl.api_watermark (source_system, brand_key, source_entity);
CREATE INDEX IF NOT EXISTS ix_batch_run_status ON etl.batch_run (status, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_batch_run_source_window ON etl.batch_run (source_system, brand_key, source_entity, requested_from, requested_to);
CREATE INDEX IF NOT EXISTS ix_api_pull_run_batch ON etl.api_pull_run (batch_id);
CREATE INDEX IF NOT EXISTS ix_api_pull_run_status_started ON etl.api_pull_run (status, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_api_gap_log_unresolved ON etl.api_gap_log (source_system, brand_key, source_entity, detected_at DESC) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_api_backfill_pending ON etl.api_backfill_request (status, priority, requested_at);
