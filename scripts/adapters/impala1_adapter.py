from adapters.base_adapter import BaseAdapter
class Impala1GameTxAdapter(BaseAdapter):
    def load_to_staging(self):
        with self.conn.cursor() as cur:
            cur.execute('''INSERT INTO staging.game_tx (batch_id,raw_event_id,brand_key,external_id,player_username,provider_name,game_name,bet_amount,payout_amount,source_created_at,source_updated_at,payload_hash) SELECT r.batch_id,r.raw_event_id,r.brand_key,r.payload->>'TransactionID',lower(trim(r.payload->>'PlayerAccount')),r.payload->>'GameProvider',r.payload->>'GameName',NULLIF(r.payload->>'TotalStakes','')::numeric,NULLIF(r.payload->>'TotalWins','')::numeric,NULLIF(r.payload->>'GameDate','')::timestamptz,NULLIF(r.payload->>'UpdateDateTime','')::timestamptz,r.payload_hash FROM raw.api_events r WHERE r.batch_id=%s AND r.brand_key=%s AND r.source_entity=%s ON CONFLICT (raw_event_id) DO NOTHING''', (self.batch_id,self.brand_key,self.source_entity))
            return cur.rowcount
