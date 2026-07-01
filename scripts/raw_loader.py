import gzip, hashlib, json
import boto3

def _insert_api_events(conn, rows):
    with conn.cursor() as cur:
        cur.executemany('''INSERT INTO raw.api_events (s3_file_id,batch_id,source_system,brand_key,source_entity,s3_line_number,payload,payload_hash) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT (s3_file_id,s3_line_number) DO NOTHING''', rows)

def load_s3_file_to_raw(conn, bucket, key, batch_id, source_system, brand_key, source_entity, aws_region, chunk_size=5000):
    s3 = boto3.client('s3', region_name=aws_region)
    head = s3.head_object(Bucket=bucket, Key=key)
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO raw.s3_files (batch_id,source_system,brand_key,source_entity,s3_bucket,s3_key,e_tag,object_size_bytes,load_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'loading') ON CONFLICT (s3_bucket,s3_key) DO UPDATE SET load_status='loading', error_message=NULL RETURNING s3_file_id''', (batch_id, source_system, brand_key, source_entity, bucket, key, head.get('ETag','').strip('"'), head.get('ContentLength')))
        s3_file_id = cur.fetchone()[0]
    obj = s3.get_object(Bucket=bucket, Key=key)
    pending, total = [], 0
    with gzip.GzipFile(fileobj=obj['Body']) as gz:
        for line_no, raw_line in enumerate(gz, start=1):
            line = raw_line.decode('utf-8').strip()
            if not line:
                continue
            payload = json.loads(line)
            payload_text = json.dumps(payload, separators=(',', ':'), sort_keys=True)
            payload_hash = hashlib.md5(payload_text.encode('utf-8')).hexdigest()
            pending.append((s3_file_id, batch_id, source_system, brand_key, source_entity, line_no, payload_text, payload_hash))
            total += 1
            if len(pending) >= chunk_size:
                _insert_api_events(conn, pending); pending.clear()
        if pending:
            _insert_api_events(conn, pending)
    with conn.cursor() as cur:
        cur.execute("UPDATE raw.s3_files SET line_count=%s, load_status='loaded', raw_load_completed_at=now() WHERE s3_file_id=%s", (total, s3_file_id))
    return {'s3_file_id': s3_file_id, 'line_count': total}
