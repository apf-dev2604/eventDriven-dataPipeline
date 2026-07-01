import importlib, logging, re
import psycopg
from raw_loader import load_s3_file_to_raw
LOG = logging.getLogger('pipeline_runner')
PART_RE = re.compile(r'(?:^|/)brand=([^/]+)/entity=([^/]+)/.*batch_id=([^/]+)/')

def parse_metadata_from_key(key):
    m = PART_RE.search(key)
    if not m:
        raise ValueError(f'Cannot parse brand/entity/batch_id from S3 key: {key}')
    return m.group(1), m.group(2), m.group(3)

def load_adapter(adapter_path):
    module_name, class_name = adapter_path.split(':')
    module = importlib.import_module(module_name)
    return getattr(module, class_name)

def run_pipeline(bucket, key, cfg):
    brand_key, source_entity, batch_id = parse_metadata_from_key(key)
    dsn = cfg['database']['dsn']
    try:
        with psycopg.connect(dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE etl.batch_run SET status=%s WHERE batch_id=%s', ('processing', batch_id))
            raw_result = load_s3_file_to_raw(conn, bucket, key, batch_id, 'Provider API', brand_key, source_entity, cfg['aws']['region'], int(cfg['worker'].get('chunk_size',5000)))
            AdapterClass = load_adapter(cfg['adapters'][brand_key][source_entity])
            adapter = AdapterClass(conn, batch_id, brand_key, source_entity)
            staging_count = adapter.load_to_staging()
            with conn.cursor() as cur:
                cur.execute('CALL etl.process_batch(%s::uuid)', (batch_id,))
            conn.commit()
        return {'success': True, 'batch_id': batch_id, 'raw': raw_result, 'staging_count': staging_count}
    except Exception as exc:
        LOG.exception('pipeline_failed')
        return {'success': False, 'batch_id': batch_id, 'error': str(exc)}
