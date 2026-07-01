-- Nexus V2 - process_batch template with delete-before-insert order
CREATE OR REPLACE PROCEDURE etl.process_batch(p_batch_id uuid)
LANGUAGE plpgsql
AS $$
DECLARE
    v_run_type text;
BEGIN
    SELECT run_type INTO v_run_type FROM etl.batch_run WHERE batch_id = p_batch_id;
    IF v_run_type IS NULL THEN RAISE EXCEPTION 'Unknown batch_id: %', p_batch_id; END IF;

    UPDATE etl.batch_run SET status = 'processing' WHERE batch_id = p_batch_id;

    -- Phase 5A: source-delete reconciliation first.
    CALL etl.process_game_tx_source_deletes(p_batch_id);

    -- Phase 5B: final insert/update should be implemented here or called here.
    -- Your real upsert must reactivate rows that reappear in source by clearing source_deleted fields.

    UPDATE etl.batch_run SET status = 'completed', completed_at = now() WHERE batch_id = p_batch_id;
EXCEPTION WHEN OTHERS THEN
    UPDATE etl.batch_run SET status = 'failed', error_message = SQLERRM, completed_at = now() WHERE batch_id = p_batch_id;
    RAISE;
END;
$$;
