#!/usr/bin/env python3
import json, logging, os, signal, sys, time
from urllib.parse import unquote_plus
import boto3, yaml
from botocore.config import Config as BotoConfig
from pipeline_runner import run_pipeline

LOG = logging.getLogger('sqs_worker')
STOP = False

def setup_logging():
    logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'), format='%(asctime)s %(levelname)s %(name)s %(message)s')

def load_config():
    with open(os.getenv('NEXUS_CONFIG','/etc/nexus-v2/pipeline_config.yaml'), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def handle_signal(signum, frame):
    global STOP
    STOP = True

def parse_s3_event_message(message_body):
    body = json.loads(message_body)
    if 'Message' in body and isinstance(body['Message'], str):
        body = json.loads(body['Message'])
    for rec in body.get('Records', []):
        s3 = rec.get('s3', {})
        bucket = s3.get('bucket', {}).get('name')
        key = s3.get('object', {}).get('key')
        if bucket and key:
            yield bucket, unquote_plus(key)

def process_one_message(sqs, queue_url, msg, cfg):
    receipt_handle = msg['ReceiptHandle']
    bucket_keys = list(parse_s3_event_message(msg['Body']))
    if not bucket_keys:
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return True
    success = True
    for bucket, key in bucket_keys:
        result = run_pipeline(bucket=bucket, key=key, cfg=cfg)
        if not result.get('success'):
            success = False
            break
    if success:
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
    return success

def main():
    setup_logging()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    cfg = load_config()
    aws = cfg['aws']
    sqs = boto3.client('sqs', region_name=aws['region'], config=BotoConfig(retries={'max_attempts':5,'mode':'standard'}))
    queue_url = aws['sqs_queue_url']
    while not STOP:
        try:
            resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=int(aws.get('max_messages',1)), WaitTimeSeconds=int(aws.get('wait_time_seconds',20)), VisibilityTimeout=int(aws.get('visibility_timeout_seconds',900)), MessageAttributeNames=['All'], AttributeNames=['All'])
            for msg in resp.get('Messages', []):
                process_one_message(sqs, queue_url, msg, cfg)
            if not resp.get('Messages'):
                time.sleep(float(aws.get('idle_sleep_seconds',2)))
        except Exception:
            LOG.exception('worker_loop_exception')
            time.sleep(10)
    return 0

if __name__ == '__main__':
    sys.exit(main())
