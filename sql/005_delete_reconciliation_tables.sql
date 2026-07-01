-- Nexus V2 - Source delete reconciliation tables
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS final_history;

CREATE TABLE IF NOT EXISTS etl.reconciliation_scope (
    scope_id bigserial PRIMARY KEY,
    source_system text NOT NULL,
    brand_key text NOT NULL,
    source_entity text NOT NULL,
    scope_type text NOT NULL DEFAULT 'createddate_snapshot',
    scope_from timestamptz NOT NULL,
    scope_to timestamptz NOT NULL,
    settled_from timestamptz,
    settled_to timestamptz,
    priority integer NOT NULL DEFAULT 100,
    enabled boolean NOT NULL DEFAULT true,
    allow_delete_reconciliation boolean NOT NULL DEFAULT true,
    last_run_at timestamptz,
    next_run_at timestamptz NOT NULL DEFAULT now(),
    last_batch_id uuid,
    last_status text,
    last_record_count integer,
    last_delete_count integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_recon_scope_window CHECK (scope_to > scope_from),
    CONSTRAINT ck_recon_settled_window CHECK ((settled_from IS NULL AND settled_to IS NULL) OR (settled_from IS NOT NULL AND settled_to IS NOT NULL AND settled_to > settled_from))
);

CREATE INDEX IF NOT EXISTS ix_reconciliation_scope_due ON etl.reconciliation_scope (enabled, next_run_at, priority);
CREATE INDEX IF NOT EXISTS ix_reconciliation_scope_key ON etl.reconciliation_scope (source_system, brand_key, source_entity, scope_from, scope_to);

CREATE TABLE IF NOT EXISTS etl.source_delete_audit (
    delete_audit_id bigserial PRIMARY KEY,
    batch_id uuid NOT NULL,
    source_system text NOT NULL,
    brand_key text NOT NULL,
    source_entity text NOT NULL,
    run_type text NOT NULL,
    comparison_scope text NOT NULL,
    creation_from timestamptz NOT NULL,
    creation_to timestamptz NOT NULL,
    settled_from timestamptz,
    settled_to timestamptz,
    final_rows_checked integer NOT NULL DEFAULT 0,
    source_rows_in_batch integer NOT NULL DEFAULT 0,
    rows_written_to_history integer NOT NULL DEFAULT 0,
    rows_marked_deleted integer NOT NULL DEFAULT 0,
    rows_reactivated integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'started' CHECK (status IN ('started','completed','skipped','failed')),
    skip_reason text,
    error_message text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_source_delete_audit_batch ON etl.source_delete_audit (batch_id);
CREATE INDEX IF NOT EXISTS ix_source_delete_audit_key_time ON etl.source_delete_audit (brand_key, source_entity, creation_from, creation_to, started_at DESC);

CREATE TABLE IF NOT EXISTS final_history.gameTX_delete_history (
    history_id bigserial PRIMARY KEY,
    batch_id uuid NOT NULL,
    deleted_detected_at timestamptz NOT NULL DEFAULT now(),
    final_game_tx_id uuid,
    brand_key text,
    platform text,
    external_id text,
    player_id uuid,
    player_username text,
    creation_date timestamptz,
    settled_date timestamptz,
    delete_reason text NOT NULL,
    delete_method text NOT NULL DEFAULT 'missing_from_createddate_snapshot',
    old_row jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_gameTX_delete_history_batch ON final_history.gameTX_delete_history (batch_id);
CREATE INDEX IF NOT EXISTS ix_gameTX_delete_history_key ON final_history.gameTX_delete_history (brand_key, platform, external_id);

CREATE TABLE IF NOT EXISTS staging.game_tx_source_keys (
    source_key_id bigserial PRIMARY KEY,
    batch_id uuid NOT NULL,
    brand_key text NOT NULL,
    platform text,
    external_id text NOT NULL,
    creation_date timestamptz,
    settled_date timestamptz,
    raw_event_id bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (batch_id, brand_key, platform, external_id)
);
CREATE INDEX IF NOT EXISTS ix_game_tx_source_keys_compare ON staging.game_tx_source_keys (batch_id, brand_key, platform, external_id);
CREATE INDEX IF NOT EXISTS ix_game_tx_source_keys_date ON staging.game_tx_source_keys (batch_id, brand_key, creation_date, settled_date);
