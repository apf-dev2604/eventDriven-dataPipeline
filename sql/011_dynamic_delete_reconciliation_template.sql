-- Nexus V2 - Dynamic delete reconciliation template
-- Purpose:
--   Show how the production logic should work when date fields differ by brand/entity.
--   This file is a template because final table column names differ per entity.
--
-- Production recommendation:
--   For each high-volume entity, implement a specific optimized procedure
--   using this exact pattern. Keep the rule table generic, but keep SQL optimized.
--
-- Pattern:
--   1. Read etl.batch_run.
--   2. Read etl.entity_batch_rule.
--   3. Validate allowed run_type and complete batch.
--   4. Compare final active business_key against staging.source_batch_keys.
--   5. Insert missing final rows into final_history.<entity>_delete_history.
--   6. Soft-delete missing final rows.
--   7. Upsert current staging rows and reactivate if needed.

-- Example for gameTX remains in 007_delete_reconciliation_procedure.sql.
-- For other entities, create procedures like:
--   etl.process_wallet_tx_source_deletes(batch_id)
--   etl.process_player_source_deletes(batch_id) -- if source delete is allowed for players
--
-- Recommended business key generation examples:
--   gameTx:   lower(brand_key) || '|' || lower(coalesce(platform,'')) || '|' || external_id
--   walletTx: lower(brand_key) || '|' || lower(coalesce(platform,'')) || '|' || reference_id
--   player:   lower(brand_key) || '|' || lower(normalized_username)

-- Helper function to standardize key creation.
CREATE OR REPLACE FUNCTION etl.make_business_key(VARIADIC p_parts text[])
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT array_to_string(
        ARRAY(
            SELECT lower(trim(coalesce(x, '')))
            FROM unnest(p_parts) AS x
        ),
        '|'
    );
$$;
