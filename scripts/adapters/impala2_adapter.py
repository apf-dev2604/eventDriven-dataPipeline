from adapters.base_adapter import BaseAdapter
class Impala2GameTxAdapter(BaseAdapter):
    def load_to_staging(self):
        with self.conn.cursor() as cur:
            cur.execute('''INSERT INTO staging.game_tx (batch_id,raw_event_id,brand_key,platform,external_id,round_id,player_username,provider_name,game_name,game_type,bet_amount,valid_bet,payout_amount,source_created_at,source_updated_at,payload_hash) SELECT r.batch_id,r.raw_event_id,r.brand_key,r.payload->'platform'->>'name',r.payload->>'id',r.payload->>'vendorRoundId',lower(trim(r.payload->'member'->>'name')),r.payload->'game'->>'provider',r.payload->'game'->>'name',r.payload->'game'->>'type',NULLIF(r.payload->>'bet','')::numeric,NULLIF(r.payload->>'validBet','')::numeric,NULLIF(r.payload->>'payout','')::numeric,NULLIF(r.payload->>'dateTimeCreated','')::timestamptz,NULLIF(r.payload->>'dateTimeLastUpdated','')::timestamptz,r.payload_hash FROM raw.api_events r WHERE r.batch_id=%s AND r.brand_key=%s AND r.source_entity=%s ON CONFLICT (raw_event_id) DO NOTHING''', (self.batch_id,self.brand_key,self.source_entity))
            return cur.rowcount
class Impala2PlayerAdapter(BaseAdapter):
    def load_to_staging(self):
        return 0
class Impala2WalletAdapter(BaseAdapter):
    def load_to_staging(self):
        return 0
