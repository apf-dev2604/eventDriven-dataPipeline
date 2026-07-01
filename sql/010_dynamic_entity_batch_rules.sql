-- Nexus V2 - Dynamic brand/entity batch rules
-- Purpose:
--   Remove hard-coding of createdDate. Every brand/entity can define its own
--   source date field, final date column, business key, lookback policy, and
--   delete-reconciliation behavior.

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS etl.entity_batch_rule (
    rule_id bigserial PRIMARY KEY,

    source_system text NOT NULL,
    brand_key text NOT NULL,
    source_entity text NOT NULL,

    -- Source/API field used for pulling the batch window.
    -- Examples: createdDate, settledDate, transactionDate, updatedAt, registeredDate.
    source_batch_date_field text NOT NULL,

    -- Final table column used for limiting delete comparison scope.
    -- Examples: creationDate, settledDate, transactionDate.
    final_scope_date_column text NOT NULL,

    -- Stable fields used to identify the same record across source and final.
    -- Recommended examples:
    --   gameTx:   brand_key + platform + external_id
    --   deposits: brand_key + platform + reference_id
    --   players:  brand_key + normalized_username or external_player_id
    business_key_fields text[] NOT NULL,

    -- Final table and source key table target. This lets one procedure route dynamically.
    final_schema text NOT NULL DEFAULT 'final_consolidated',
    final_table text NOT NULL,
    staging_table text NOT NULL,

    -- Safety controls.
    allow_delete_reconciliation boolean NOT NULL DEFAULT false,
    soft_delete_only boolean NOT NULL DEFAULT true,
    require_complete_snapshot boolean NOT NULL DEFAULT true,

    -- Near-real-time and delayed-data policy.
    current_pull_frequency_minutes integer NOT NULL DEFAULT 5,
    current_overlap_minutes integer NOT NULL DEFAULT 10,
    safety_delay_minutes integer NOT NULL DEFAULT 5,
    rolling_lookback_days integer NOT NULL DEFAULT 3,
    lookback_slice_minutes integer NOT NULL DEFAULT 60,
    max_lookback_slices_per_run integer NOT NULL DEFAULT 2,

    enabled boolean NOT NULL DEFAULT true,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (source_system, brand_key, source_entity)
);

CREATE INDEX IF NOT EXISTS ix_entity_batch_rule_enabled
ON etl.entity_batch_rule (enabled, source_system, brand_key, source_entity);

-- Generic key table used for fast source-vs-final delete comparison.
-- Adapters should write one row per source record key for each batch.
CREATE TABLE IF NOT EXISTS staging.source_batch_keys (
    source_key_id bigserial PRIMARY KEY,

    batch_id uuid NOT NULL,
    source_system text NOT NULL,
    brand_key text NOT NULL,
    source_entity text NOT NULL,

    scope_date_field text NOT NULL,
    scope_from timestamptz NOT NULL,
    scope_to timestamptz NOT NULL,

    -- Dynamic identity key, generated consistently by adapter and final upsert logic.
    -- Example: inplay|platformA|abc123
    business_key text NOT NULL,

    raw_event_id bigint,
    payload_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (batch_id, business_key)
);

CREATE INDEX IF NOT EXISTS ix_source_batch_keys_compare
ON staging.source_batch_keys (batch_id, brand_key, source_entity, business_key);

CREATE INDEX IF NOT EXISTS ix_source_batch_keys_scope
ON staging.source_batch_keys (source_system, brand_key, source_entity, scope_from, scope_to);

-- Example rules. Adjust names to match real providers/entities.
INSERT INTO etl.entity_batch_rule (
    source_system, brand_key, source_entity,
    source_batch_date_field, final_scope_date_column,
    business_key_fields,
    final_table, staging_table,
    allow_delete_reconciliation,
    rolling_lookback_days
)
VALUES
('Provider API','inplay','gameTx','createdDate','creationDate',ARRAY['brand_key','platform','external_id'],'gameTX','game_tx',true,3),
('Provider API','inplay','deposits','transactionDate','transactionDate',ARRAY['brand_key','platform','reference_id'],'walletTx','wallet_tx',true,3),
('Provider API','inplay','withdrawals','transactionDate','transactionDate',ARRAY['brand_key','platform','reference_id'],'walletTx','wallet_tx',true,3),
('Provider API','inplay','players','registeredDate','createdAt',ARRAY['brand_key','normalized_username'],'AccountDetails','players',false,3)
ON CONFLICT (source_system, brand_key, source_entity) DO NOTHING;
