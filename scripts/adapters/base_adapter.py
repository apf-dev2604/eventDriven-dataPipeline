class BaseAdapter:
    def __init__(self, conn, batch_id, brand_key, source_entity):
        self.conn = conn
        self.batch_id = batch_id
        self.brand_key = brand_key
        self.source_entity = source_entity
    def load_to_staging(self):
        raise NotImplementedError
