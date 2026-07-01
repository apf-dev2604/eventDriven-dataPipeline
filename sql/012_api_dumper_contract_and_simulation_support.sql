-- Nexus V2 - API Dumper contract and simulation support
-- Purpose:
--   Make the API Dumper interface explicit and compatible with the newer run types.
--   The API Developer may write only to ETL control tables. DBA/Data Engineering owns raw, staging, final, history, and quarantine.

CREATE SCHEMA IF NOT EXISTS etl;

-- Patch run types for newer pipeline modes.
ALTER TABLE etl.batch_run
DROP CONSTRAINT IF EXISTS batch_run_run_type_check;

ALTER TABLE etl.batch_run
ADD CONSTRAINT batch_run_run_type_check
CHECK (
    run_type IN (
        'incremental',
        'incremental_current',
        'createddate_snapshot',
        'backfill',
        'manual_replay',
        'manual_replay_snapshot'
    )
);

-- Track external/API-side batch id when the API Dumper generates its own id.
ALTER TABLE etl.batch_run
ADD COLUMN IF NOT EXISTS external_batch_id text,
ADD COLUMN IF NOT EXISTS date_field text,
ADD COLUMN IF NOT EXISTS is_complete_snapshot boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS pagination_complete boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS manifest_s3_bucket text,
ADD COLUMN IF NOT EXISTS manifest_s3_key text,
ADD COLUMN IF NOT EXISTS manifest_payload jsonb;

CREATE INDEX IF NOT EXISTS ix_batch_run_external_batch_id
ON etl.batch_run (external_batch_id);

CREATE INDEX IF NOT EXISTS ix_batch_run_s3_key
ON etl.batch_run (s3_bucket, s3_key);

-- Optional S3 arrival log used by DBA/Data Engineering side when SQS receives an S3 event.
CREATE TABLE IF NOT EXISTS etl.s3_arrival_log (
    arrival_id bigserial PRIMARY KEY,
    batch_id uuid,
    s3_bucket text NOT NULL,
    s3_key text NOT NULL,
    event_name text,
    event_time timestamptz,
    manifest_s3_bucket text,
    manifest_s3_key text,
    status text NOT NULL DEFAULT 'received'
        CHECK (status IN ('received','registered','processing','completed','failed','duplicate')),
    error_message text,
    received_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (s3_bucket, s3_key)
);

CREATE INDEX IF NOT EXISTS ix_s3_arrival_log_status
ON etl.s3_arrival_log (status, received_at DESC);

-- Optional contract view for API developers to know what to pull.
CREATE OR REPLACE VIEW etl.v_api_dumper_worklist AS
SELECT
    c.source_system,
    c.brand_key,
    c.source_entity,
    c.api_endpoint,
    c.pull_frequency_minutes,
    c.overlap_minutes,
    c.safety_delay_minutes,
    c.default_run_type,
    c.s3_bucket,
    c.s3_prefix,
    r.source_batch_date_field,
    r.final_scope_date_column,
    r.business_key_fields,
    r.allow_delete_reconciliation,
    r.rolling_lookback_days,
    r.lookback_slice_minutes,
    w.last_successful_from,
    w.last_successful_to,
    w.last_batch_id
FROM etl.api_pull_config c
LEFT JOIN etl.api_watermark w
  ON w.source_system = c.source_system
 AND w.brand_key = c.brand_key
 AND w.source_entity = c.source_entity
LEFT JOIN etl.entity_batch_rule r
  ON r.source_system = c.source_system
 AND r.brand_key = c.brand_key
 AND r.source_entity = c.source_entity
WHERE c.enabled = true
  AND COALESCE(r.enabled, true) = true;

-- Example API Developer role grants. Run as DBA and adjust role names.
-- GRANT SELECT ON etl.api_pull_config, etl.entity_batch_rule, etl.v_api_dumper_worklist, etl.reconciliation_scope TO nexus_dumper;
-- GRANT SELECT, INSERT, UPDATE ON etl.api_watermark, etl.batch_run, etl.api_pull_run, etl.api_gap_log, etl.api_backfill_request TO nexus_dumper;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA etl TO nexus_dumper;
