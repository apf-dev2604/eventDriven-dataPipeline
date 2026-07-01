#!/usr/bin/env python3
"""
S3/SQS POC tester for Nexus V2.

Purpose:
  Prove that:
  1. A JSONL gzip file can be uploaded to S3.
  2. S3 ObjectCreated notification sends a message to SQS.
  3. The SQS message contains the S3 bucket/key.
  4. The worker can later process the message.

This script does not write final data. It only tests AWS event plumbing.

Example:
  python scripts/simulation/s3_sqs_poc_tester.py \
    --bucket nexus-v2-raw-dev \
    --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/nexus-v2-s3-events \
    --region ap-southeast-1 \
    --brand inplay --entity gameTx
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
import uuid
from datetime import datetime, timezone

import boto3


def make_jsonl_gz() -> bytes:
    rows = [
        {
            "brand": "inplay",
            "entity": "gameTx",
            "platform": "platformA",
            "externalId": "POC001",
            "username": "poc_player",
            "createdDate": "2026-05-11T10:15:00+08:00",
            "settledDate": "2026-05-11T10:30:00+08:00",
            "betAmount": 100,
            "payout": 50,
            "status": "SETTLED",
        }
    ]
    raw = b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in rows)
    return gzip.compress(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--queue-url", required=True)
    ap.add_argument("--region", default="ap-southeast-1")
    ap.add_argument("--brand", default="inplay")
    ap.add_argument("--entity", default="gameTx")
    ap.add_argument("--timeout-seconds", type=int, default=60)
    args = ap.parse_args()

    s3 = boto3.client("s3", region_name=args.region)
    sqs = boto3.client("sqs", region_name=args.region)

    batch_id = str(uuid.uuid4())
    key = (
        f"raw/source_system=provider_api/brand={args.brand}/entity={args.entity}/"
        f"run_type=createddate_snapshot/date_field=createdDate/"
        f"window_from=20260511T100000+0800/window_to=20260511T110000+0800/"
        f"batch_id={batch_id}/part-0001.jsonl.gz"
    )

    print(f"Uploading test object: s3://{args.bucket}/{key}")
    s3.put_object(
        Bucket=args.bucket,
        Key=key,
        Body=make_jsonl_gz(),
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
        ServerSideEncryption="aws:kms",
    )

    deadline = time.time() + args.timeout_seconds
    print("Waiting for SQS message...")
    while time.time() < deadline:
        resp = sqs.receive_message(
            QueueUrl=args.queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10,
            VisibilityTimeout=30,
        )
        msgs = resp.get("Messages", [])
        for msg in msgs:
            body = json.loads(msg["Body"])
            body_text = json.dumps(body)
            if key in body_text:
                print("SUCCESS: SQS received matching S3 event.")
                print(json.dumps({
                    "batch_id": batch_id,
                    "s3_bucket": args.bucket,
                    "s3_key": key,
                    "sqs_message_id": msg.get("MessageId"),
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }, indent=2))
                # Do not delete by default in case worker needs to process it.
                print("Message not deleted by tester. Let worker process or purge manually if needed.")
                return 0
            else:
                print("Received unrelated SQS message; leaving it for worker.")

    print("FAILED: No matching S3 event was received in SQS before timeout.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
