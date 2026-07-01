-- Nexus V2 - Final table soft-delete columns
-- Adjust column names if your actual final table uses quoted camelCase.
ALTER TABLE final_consolidated.gameTX
ADD COLUMN IF NOT EXISTS is_source_deleted boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS source_deleted_at timestamptz,
ADD COLUMN IF NOT EXISTS source_deleted_batch_id uuid,
ADD COLUMN IF NOT EXISTS source_delete_reason text,
ADD COLUMN IF NOT EXISTS source_reactivated_at timestamptz,
ADD COLUMN IF NOT EXISTS source_reactivated_batch_id uuid;

CREATE INDEX IF NOT EXISTS ix_final_gameTX_active_delete_compare
ON final_consolidated.gameTX (brand, platform, externalId, creationDate, settledDate)
WHERE is_source_deleted = false;

CREATE INDEX IF NOT EXISTS ix_final_gameTX_deleted_lookup
ON final_consolidated.gameTX (brand, platform, externalId)
WHERE is_source_deleted = true;
