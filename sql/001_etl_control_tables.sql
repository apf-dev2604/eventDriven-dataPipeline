CREATE SCHEMA IF NOT EXISTS etl;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS etl.api_pull_config (
  config_id bigserial PRIMARY KEY,
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  api_endpoint text,
  pull_frequency_minutes integer NOT NULL DEFAULT 5,
  overlap_minutes integer NOT NULL DEFAULT 10,
  safety_delay_minutes integer NOT NULL DEFAULT 5,
  enabled boolean NOT NULL DEFAULT true,
  default_run_type text NOT NULL DEFAULT 'incremental',
  s3_bucket text NOT NULL,
  s3_prefix text NOT NULL DEFAULT 'raw',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_system, brand_key, source_entity)
);

CREATE TABLE IF NOT EXISTS etl.api_watermark (
  watermark_id bigserial PRIMARY KEY,
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  last_successful_from timestamptz,
  last_successful_to timestamptz,
  last_batch_id uuid,
  last_s3_bucket text,
  last_s3_key text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_system, brand_key, source_entity)
);

CREATE TABLE IF NOT EXISTS etl.batch_run (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  run_type text NOT NULL CHECK (run_type IN ('incremental','backfill','manual_replay')),
  requested_from timestamptz,
  requested_to timestamptz,
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created','pulling','s3_written','queued','processing','completed','failed','cancelled')),
  s3_bucket text,
  s3_key text,
  api_record_count integer DEFAULT 0,
  raw_record_count integer DEFAULT 0,
  staging_record_count integer DEFAULT 0,
  final_insert_count integer DEFAULT 0,
  final_update_count integer DEFAULT 0,
  quarantine_count integer DEFAULT 0,
  duplicate_count integer DEFAULT 0,
  stale_count integer DEFAULT 0,
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl.api_pull_run (
  pull_run_id bigserial PRIMARY KEY,
  batch_id uuid REFERENCES etl.batch_run(batch_id),
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  run_type text NOT NULL,
  requested_from timestamptz,
  requested_to timestamptz,
  status text NOT NULL DEFAULT 'started' CHECK (status IN ('started','api_calling','api_success','api_empty','s3_writing','completed','failed')),
  api_record_count integer DEFAULT 0,
  s3_bucket text,
  s3_key text,
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS etl.api_gap_log (
  gap_id bigserial PRIMARY KEY,
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  gap_from timestamptz NOT NULL,
  gap_to timestamptz NOT NULL,
  reason_code text NOT NULL,
  severity text NOT NULL DEFAULT 'warning',
  detected_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  related_batch_id uuid,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS etl.api_backfill_request (
  backfill_id bigserial PRIMARY KEY,
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  backfill_from timestamptz NOT NULL,
  backfill_to timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed','cancelled')),
  priority integer NOT NULL DEFAULT 100,
  reason text,
  requested_by text DEFAULT current_user,
  requested_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  batch_id uuid,
  error_message text
);
