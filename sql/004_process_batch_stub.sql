CREATE OR REPLACE PROCEDURE etl.process_batch(p_batch_id uuid)
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE etl.batch_run SET status = 'processing' WHERE batch_id = p_batch_id;
  -- TODO: validate staging rows, resolve IDs, insert invalid rows to quarantine,
  -- insert/update final_consolidated, and write final_history versions.
  UPDATE etl.batch_run SET status = 'completed', completed_at = now() WHERE batch_id = p_batch_id;
EXCEPTION WHEN OTHERS THEN
  UPDATE etl.batch_run SET status = 'failed', error_message = SQLERRM, completed_at = now() WHERE batch_id = p_batch_id;
  RAISE;
END;
$$;
