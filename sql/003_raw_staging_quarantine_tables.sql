CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS rejected;
CREATE SCHEMA IF NOT EXISTS final_history;

CREATE TABLE IF NOT EXISTS raw.s3_files (
  s3_file_id bigserial PRIMARY KEY,
  batch_id uuid NOT NULL REFERENCES etl.batch_run(batch_id),
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  s3_bucket text NOT NULL,
  s3_key text NOT NULL,
  e_tag text,
  object_size_bytes bigint,
  line_count integer DEFAULT 0,
  load_status text NOT NULL DEFAULT 'loading' CHECK (load_status IN ('loading','loaded','failed')),
  error_message text,
  raw_load_started_at timestamptz NOT NULL DEFAULT now(),
  raw_load_completed_at timestamptz,
  UNIQUE (s3_bucket, s3_key)
);

CREATE TABLE IF NOT EXISTS raw.api_events (
  raw_event_id bigserial PRIMARY KEY,
  s3_file_id bigint NOT NULL REFERENCES raw.s3_files(s3_file_id),
  batch_id uuid NOT NULL REFERENCES etl.batch_run(batch_id),
  source_system text NOT NULL,
  brand_key text NOT NULL,
  source_entity text NOT NULL,
  s3_line_number integer NOT NULL,
  payload jsonb NOT NULL,
  payload_hash text NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (s3_file_id, s3_line_number)
);
CREATE INDEX IF NOT EXISTS ix_raw_api_events_batch_entity ON raw.api_events (batch_id, brand_key, source_entity);
CREATE INDEX IF NOT EXISTS ix_raw_api_events_payload_hash ON raw.api_events (payload_hash);

CREATE TABLE IF NOT EXISTS staging.players (
  staging_id bigserial PRIMARY KEY,
  batch_id uuid NOT NULL,
  raw_event_id bigint NOT NULL UNIQUE,
  brand_key text NOT NULL,
  player_username text,
  player_external_id text,
  email text,
  mobile_number text,
  status text,
  is_active boolean,
  is_blocked boolean,
  is_verified boolean,
  wallet_balance numeric(18,4),
  source_created_at timestamptz,
  source_updated_at timestamptz,
  payload_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.wallet_tx (
  staging_id bigserial PRIMARY KEY,
  batch_id uuid NOT NULL,
  raw_event_id bigint NOT NULL UNIQUE,
  brand_key text NOT NULL,
  platform text,
  transaction_type text,
  reference_id text,
  player_username text,
  amount numeric(18,4),
  status text,
  payment_gateway text,
  domain text,
  source_created_at timestamptz,
  source_updated_at timestamptz,
  payload_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.game_tx (
  staging_id bigserial PRIMARY KEY,
  batch_id uuid NOT NULL,
  raw_event_id bigint NOT NULL UNIQUE,
  brand_key text NOT NULL,
  platform text,
  external_id text,
  round_id text,
  player_username text,
  provider_name text,
  game_name text,
  game_type text,
  bet_amount numeric(18,4),
  valid_bet numeric(18,4),
  payout_amount numeric(18,4),
  source_created_at timestamptz,
  source_updated_at timestamptz,
  payload_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_staging_players_batch ON staging.players(batch_id, brand_key);
CREATE INDEX IF NOT EXISTS ix_staging_wallet_batch ON staging.wallet_tx(batch_id, brand_key);
CREATE INDEX IF NOT EXISTS ix_staging_game_batch ON staging.game_tx(batch_id, brand_key);

CREATE TABLE IF NOT EXISTS rejected.transaction_quarantine (
  quarantine_id bigserial PRIMARY KEY,
  batch_id uuid NOT NULL,
  raw_event_id bigint,
  staging_table text,
  staging_id bigint,
  brand_key text,
  source_entity text,
  reason_code text NOT NULL,
  reason_detail text,
  payload jsonb,
  reprocess_status text NOT NULL DEFAULT 'pending' CHECK (reprocess_status IN ('pending','reprocessed','ignored','failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  reprocessed_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_quarantine_pending ON rejected.transaction_quarantine (reprocess_status, created_at);
CREATE INDEX IF NOT EXISTS ix_quarantine_batch ON rejected.transaction_quarantine (batch_id);
