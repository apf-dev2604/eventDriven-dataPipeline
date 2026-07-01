-- Nexus V2 - Safe source-delete reconciliation procedure
-- Align final table column names with your real DDL before production deployment.
CREATE OR REPLACE PROCEDURE etl.process_game_tx_source_deletes(p_batch_id uuid)
LANGUAGE plpgsql
AS $$
DECLARE
    v_source_system text;
    v_brand_key text;
    v_source_entity text;
    v_run_type text;
    v_creation_from timestamptz;
    v_creation_to timestamptz;
    v_raw_count integer;
    v_staging_count integer;
    v_final_checked integer;
    v_history_count integer;
    v_deleted_count integer;
BEGIN
    SELECT source_system, brand_key, source_entity, run_type, requested_from, requested_to
    INTO v_source_system, v_brand_key, v_source_entity, v_run_type, v_creation_from, v_creation_to
    FROM etl.batch_run
    WHERE batch_id = p_batch_id;

    IF v_source_system IS NULL THEN
        RAISE EXCEPTION 'Unknown batch_id: %', p_batch_id;
    END IF;

    IF v_run_type NOT IN ('createddate_snapshot', 'manual_replay_snapshot') THEN
        INSERT INTO etl.source_delete_audit (batch_id, source_system, brand_key, source_entity, run_type, comparison_scope, creation_from, creation_to, status, skip_reason, completed_at)
        VALUES (p_batch_id, v_source_system, v_brand_key, v_source_entity, v_run_type, 'createdDate', v_creation_from, v_creation_to, 'skipped', 'run_type is not allowed to perform delete reconciliation', now());
        RETURN;
    END IF;

    SELECT count(*) INTO v_raw_count FROM raw.api_events WHERE batch_id = p_batch_id;
    SELECT count(*) INTO v_staging_count FROM staging.game_tx WHERE batch_id = p_batch_id;
    IF v_raw_count = 0 OR v_staging_count = 0 THEN
        INSERT INTO etl.source_delete_audit (batch_id, source_system, brand_key, source_entity, run_type, comparison_scope, creation_from, creation_to, source_rows_in_batch, status, skip_reason, completed_at)
        VALUES (p_batch_id, v_source_system, v_brand_key, v_source_entity, v_run_type, 'createdDate', v_creation_from, v_creation_to, v_staging_count, 'skipped', 'raw or staging rows are empty; unsafe to compare for deletes', now());
        RETURN;
    END IF;

    SELECT count(*) INTO v_final_checked
    FROM final_consolidated.gameTX f
    WHERE f.brand = v_brand_key
      AND f.creationDate >= v_creation_from
      AND f.creationDate < v_creation_to
      AND f.is_source_deleted = false;

    INSERT INTO etl.source_delete_audit (batch_id, source_system, brand_key, source_entity, run_type, comparison_scope, creation_from, creation_to, final_rows_checked, source_rows_in_batch, status)
    VALUES (p_batch_id, v_source_system, v_brand_key, v_source_entity, v_run_type, 'createdDate', v_creation_from, v_creation_to, v_final_checked, v_staging_count, 'started');

    INSERT INTO final_history.gameTX_delete_history (batch_id, final_game_tx_id, brand_key, platform, external_id, player_id, player_username, creation_date, settled_date, delete_reason, delete_method, old_row)
    SELECT p_batch_id, f.id, f.brand, f.platform, f.externalId, f.playerId, f.playerUserName, f.creationDate, f.settledDate, 'missing_from_createddate_snapshot', 'soft_delete_before_final_upsert', to_jsonb(f)
    FROM final_consolidated.gameTX f
    WHERE f.brand = v_brand_key
      AND f.creationDate >= v_creation_from
      AND f.creationDate < v_creation_to
      AND f.is_source_deleted = false
      AND NOT EXISTS (
          SELECT 1 FROM staging.game_tx s
          WHERE s.batch_id = p_batch_id
            AND s.brand_key = f.brand
            AND COALESCE(s.platform, '') = COALESCE(f.platform, '')
            AND s.external_id = f.externalId
      );
    GET DIAGNOSTICS v_history_count = ROW_COUNT;

    UPDATE final_consolidated.gameTX f
    SET is_source_deleted = true,
        source_deleted_at = now(),
        source_deleted_batch_id = p_batch_id,
        source_delete_reason = 'missing_from_createddate_snapshot'
    WHERE f.brand = v_brand_key
      AND f.creationDate >= v_creation_from
      AND f.creationDate < v_creation_to
      AND f.is_source_deleted = false
      AND NOT EXISTS (
          SELECT 1 FROM staging.game_tx s
          WHERE s.batch_id = p_batch_id
            AND s.brand_key = f.brand
            AND COALESCE(s.platform, '') = COALESCE(f.platform, '')
            AND s.external_id = f.externalId
      );
    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;

    UPDATE etl.source_delete_audit
    SET rows_written_to_history = v_history_count,
        rows_marked_deleted = v_deleted_count,
        status = 'completed',
        completed_at = now()
    WHERE batch_id = p_batch_id AND status = 'started';
EXCEPTION WHEN OTHERS THEN
    UPDATE etl.source_delete_audit SET status = 'failed', error_message = SQLERRM, completed_at = now()
    WHERE batch_id = p_batch_id AND status = 'started';
    RAISE;
END;
$$;
