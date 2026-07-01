#!/usr/bin/env python3
"""
Nexus V2 API Dumper Simulator.

Purpose:
  This script demonstrates what the API Developer/Dumper should do:
  - read ETL control tables,
  - create etl.batch_run and etl.api_pull_run,
  - call a provider API sample,
  - write JSONL gzip to S3 or local folder,
  - update ETL control tables,
  - update watermark only after successful file write,
  - create gap/backfill rows on failure.

This script is for POC/simulation and developer handoff documentation.
Production code should use the same DB table sequence but with the real provider API client.

Examples:
  # 1. Current/incremental style pull based on watermark
  python scripts/simulation/api_dumper_simulator.py \
    --dsn "$DATABASE_URL" \
    --source-system "Provider API" --brand inplay --entity gameTx \
    --api-base-url http://127.0.0.1:8088 \
    --s3-bucket nexus-v2-raw-dev --s3-prefix raw \
    --local-s3-dir /tmp/nexus_s3 \
    --run-type incremental_current

  # 2. Snapshot pull used for source-delete simulation
  python scripts/simulation/api_dumper_simulator.py \
    --dsn "$DATABASE_URL" \
    --source-system "Provider API" --brand inplay --entity gameTx \
    --api-base-url http://127.0.0.1:8088 \
    --s3-bucket nexus-v2-raw-dev --s3-prefix raw \
    --local-s3-dir /tmp/nexus_s3 \
    --run-type createddate_snapshot \
    --window-from 2026-05-11T10:00:00+08:00 \
    --window-to   2026-05-11T11:00:00+08:00
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

import boto3
import psycopg


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dt_to_api(value: datetime) -> str:
    return value.isoformat()


def get_one(cur, sql: str, params: tuple) -> Optional[tuple]:
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_watermark(cur, source_system: str, brand: str, entity: str) -> None:
    cur.execute(
        """
        INSERT INTO etl.api_watermark (source_system, brand_key, source_entity)
        VALUES (%s, %s, %s)
        ON CONFLICT (source_system, brand_key, source_entity) DO NOTHING
        """,
        (source_system, brand, entity),
    )


def read_config_and_rule(cur, source_system: str, brand: str, entity: str) -> Dict[str, Any]:
    # API Developer lookup: what to pull and how to pull it.
    cur.execute(
        """
        SELECT
            c.api_endpoint,
            c.pull_frequency_minutes,
            c.overlap_minutes,
            c.safety_delay_minutes,
            c.default_run_type,
            c.s3_bucket,
            c.s3_prefix,
            COALESCE(r.source_batch_date_field, 'createdDate') AS source_batch_date_field,
            COALESCE(r.allow_delete_reconciliation, false) AS allow_delete_reconciliation
        FROM etl.api_pull_config c
        LEFT JOIN etl.entity_batch_rule r
          ON r.source_system = c.source_system
         AND r.brand_key = c.brand_key
         AND r.source_entity = c.source_entity
        WHERE c.source_system = %s
          AND c.brand_key = %s
          AND c.source_entity = %s
          AND c.enabled = true
        """,
        (source_system, brand, entity),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"No enabled api_pull_config found for {source_system}/{brand}/{entity}")

    keys = [
        "api_endpoint", "pull_frequency_minutes", "overlap_minutes", "safety_delay_minutes",
        "default_run_type", "s3_bucket", "s3_prefix", "source_batch_date_field",
        "allow_delete_reconciliation",
    ]
    return dict(zip(keys, row))


def compute_window(cur, source_system: str, brand: str, entity: str, cfg: Dict[str, Any]) -> Tuple[datetime, datetime]:
    ensure_watermark(cur, source_system, brand, entity)
    cur.execute(
        """
        SELECT last_successful_to
        FROM etl.api_watermark
        WHERE source_system = %s AND brand_key = %s AND source_entity = %s
        """,
        (source_system, brand, entity),
    )
    row = cur.fetchone()
    now_safe = datetime.now(timezone.utc) - timedelta(minutes=int(cfg["safety_delay_minutes"]))

    if row and row[0]:
        start = row[0] - timedelta(minutes=int(cfg["overlap_minutes"]))
    else:
        # POC default: pull the last frequency interval when no watermark exists.
        start = now_safe - timedelta(minutes=int(cfg["pull_frequency_minutes"]))

    end = now_safe
    return start, end


def create_batch(cur, *, source_system: str, brand: str, entity: str, run_type: str,
                 window_from: datetime, window_to: datetime, date_field: str,
                 complete_snapshot: bool, external_batch_id: str) -> str:
    # API Developer INSERT: register the batch before API call.
    cur.execute(
        """
        INSERT INTO etl.batch_run (
            source_system, brand_key, source_entity, run_type,
            requested_from, requested_to, status,
            external_batch_id, date_field,
            is_complete_snapshot, pagination_complete
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'created', %s, %s, %s, false)
        RETURNING batch_id
        """,
        (source_system, brand, entity, run_type, window_from, window_to,
         external_batch_id, date_field, complete_snapshot),
    )
    batch_id = str(cur.fetchone()[0])

    # API Developer INSERT: record the API attempt.
    cur.execute(
        """
        INSERT INTO etl.api_pull_run (
            batch_id, source_system, brand_key, source_entity,
            run_type, requested_from, requested_to, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'started')
        """,
        (batch_id, source_system, brand, entity, run_type, window_from, window_to),
    )
    return batch_id


def update_status(cur, batch_id: str, batch_status: str, pull_status: Optional[str] = None,
                  error_message: Optional[str] = None) -> None:
    cur.execute(
        """
        UPDATE etl.batch_run
        SET status = %s,
            error_message = COALESCE(%s, error_message),
            completed_at = CASE WHEN %s IN ('completed','failed','cancelled') THEN now() ELSE completed_at END
        WHERE batch_id = %s
        """,
        (batch_status, error_message, batch_status, batch_id),
    )
    if pull_status:
        cur.execute(
            """
            UPDATE etl.api_pull_run
            SET status = %s,
                error_message = COALESCE(%s, error_message),
                completed_at = CASE WHEN %s IN ('completed','failed') THEN now() ELSE completed_at END
            WHERE batch_id = %s
            """,
            (pull_status, error_message, pull_status, batch_id),
        )


def call_provider_api(api_base_url: str, *, brand: str, entity: str, date_field: str,
                      window_from: datetime, window_to: datetime, page_size: int = 100) -> Tuple[List[Dict[str, Any]], bool]:
    rows: List[Dict[str, Any]] = []
    page = 1
    total_pages = None

    while True:
        query = urlencode({
            "brand": brand,
            "entity": entity,
            "date_field": date_field,
            "from": dt_to_api(window_from),
            "to": dt_to_api(window_to),
            "page": page,
            "page_size": page_size,
        })
        url = f"{api_base_url.rstrip('/')}/records?{query}"
        with urlopen(url, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if not body.get("api_success"):
            raise RuntimeError(f"Provider API did not return success: {body}")
        rows.extend(body.get("records", []))
        total_pages = int(body.get("total_pages", 1))
        if page >= total_pages:
            break
        page += 1

    return rows, True


def jsonl_gz_bytes(rows: List[Dict[str, Any]]) -> bytes:
    raw = b"".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n" for r in rows)
    return gzip.compress(raw)


def write_file(*, rows: List[Dict[str, Any]], manifest: Dict[str, Any], s3_bucket: str, data_key: str,
               manifest_key: str, local_s3_dir: Optional[str], aws_region: str) -> Tuple[str, str, str]:
    body = jsonl_gz_bytes(rows)
    checksum = hashlib.sha256(body).hexdigest()
    manifest["checksum_sha256"] = checksum
    manifest["file_name"] = data_key.split("/")[-1]

    if local_s3_dir:
        base = Path(local_s3_dir) / s3_bucket
        data_path = base / data_key
        manifest_path = base / manifest_key
        data_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_bytes(body)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    else:
        s3 = boto3.client("s3", region_name=aws_region)
        s3.put_object(
            Bucket=s3_bucket,
            Key=data_key,
            Body=body,
            ContentType="application/x-ndjson",
            ContentEncoding="gzip",
            ServerSideEncryption="aws:kms",
        )
        s3.put_object(
            Bucket=s3_bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
        )

    return s3_bucket, data_key, manifest_key


def mark_s3_written(cur, *, batch_id: str, s3_bucket: str, s3_key: str, manifest_key: str,
                    manifest: Dict[str, Any], api_record_count: int, pagination_complete: bool) -> None:
    # API Developer UPDATE: mark file successfully written.
    cur.execute(
        """
        UPDATE etl.batch_run
        SET status = 's3_written',
            s3_bucket = %s,
            s3_key = %s,
            manifest_s3_bucket = %s,
            manifest_s3_key = %s,
            manifest_payload = %s::jsonb,
            api_record_count = %s,
            pagination_complete = %s
        WHERE batch_id = %s
        """,
        (s3_bucket, s3_key, s3_bucket, manifest_key, json.dumps(manifest),
         api_record_count, pagination_complete, batch_id),
    )
    cur.execute(
        """
        UPDATE etl.api_pull_run
        SET status = 'completed',
            api_record_count = %s,
            s3_bucket = %s,
            s3_key = %s,
            completed_at = now()
        WHERE batch_id = %s
        """,
        (api_record_count, s3_bucket, s3_key, batch_id),
    )


def update_watermark(cur, *, source_system: str, brand: str, entity: str,
                     window_from: datetime, window_to: datetime,
                     batch_id: str, s3_bucket: str, s3_key: str) -> None:
    # API Developer UPDATE: watermark only after successful API + S3 write.
    cur.execute(
        """
        INSERT INTO etl.api_watermark (
            source_system, brand_key, source_entity,
            last_successful_from, last_successful_to,
            last_batch_id, last_s3_bucket, last_s3_key, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (source_system, brand_key, source_entity)
        DO UPDATE SET
            last_successful_from = EXCLUDED.last_successful_from,
            last_successful_to = EXCLUDED.last_successful_to,
            last_batch_id = EXCLUDED.last_batch_id,
            last_s3_bucket = EXCLUDED.last_s3_bucket,
            last_s3_key = EXCLUDED.last_s3_key,
            updated_at = now()
        """,
        (source_system, brand, entity, window_from, window_to, batch_id, s3_bucket, s3_key),
    )


def log_failure(cur, *, source_system: str, brand: str, entity: str, window_from: datetime,
                window_to: datetime, batch_id: Optional[str], error_message: str) -> None:
    # API Developer INSERT: record gap and optional backfill request.
    cur.execute(
        """
        INSERT INTO etl.api_gap_log (
            source_system, brand_key, source_entity,
            gap_from, gap_to, reason_code, severity, related_batch_id, details
        )
        VALUES (%s, %s, %s, %s, %s, 'api_dumper_failed', 'critical', %s,
                jsonb_build_object('error_message', %s))
        """,
        (source_system, brand, entity, window_from, window_to, batch_id, error_message),
    )
    cur.execute(
        """
        INSERT INTO etl.api_backfill_request (
            source_system, brand_key, source_entity,
            backfill_from, backfill_to, priority, reason, batch_id, error_message
        )
        VALUES (%s, %s, %s, %s, %s, 10, 'API Dumper failed; needs rerun', %s, %s)
        """,
        (source_system, brand, entity, window_from, window_to, batch_id, error_message),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--source-system", default="Provider API")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--entity", required=True)
    ap.add_argument("--api-base-url", required=True)
    ap.add_argument("--run-type", default=None, choices=[
        "incremental", "incremental_current", "createddate_snapshot", "backfill", "manual_replay", "manual_replay_snapshot"
    ])
    ap.add_argument("--window-from")
    ap.add_argument("--window-to")
    ap.add_argument("--s3-bucket")
    ap.add_argument("--s3-prefix")
    ap.add_argument("--local-s3-dir", help="Write files to local folder instead of real S3. Good for offline simulation.")
    ap.add_argument("--aws-region", default="ap-southeast-1")
    ap.add_argument("--page-size", type=int, default=100)
    args = ap.parse_args()

    batch_id: Optional[str] = None
    with psycopg.connect(args.dsn, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                cfg = read_config_and_rule(cur, args.source_system, args.brand, args.entity)
                run_type = args.run_type or cfg["default_run_type"]
                date_field = cfg["source_batch_date_field"]
                s3_bucket = args.s3_bucket or cfg["s3_bucket"]
                s3_prefix = args.s3_prefix or cfg["s3_prefix"]

                if args.window_from and args.window_to:
                    window_from = parse_dt(args.window_from)
                    window_to = parse_dt(args.window_to)
                else:
                    window_from, window_to = compute_window(cur, args.source_system, args.brand, args.entity, cfg)

                complete_snapshot = run_type in ("createddate_snapshot", "manual_replay_snapshot")
                external_batch_id = f"api-{args.brand}-{args.entity}-{uuid.uuid4()}"

                batch_id = create_batch(
                    cur,
                    source_system=args.source_system,
                    brand=args.brand,
                    entity=args.entity,
                    run_type=run_type,
                    window_from=window_from,
                    window_to=window_to,
                    date_field=date_field,
                    complete_snapshot=complete_snapshot,
                    external_batch_id=external_batch_id,
                )
                conn.commit()

                update_status(cur, batch_id, "pulling", "api_calling")
                conn.commit()

                rows, pagination_complete = call_provider_api(
                    args.api_base_url,
                    brand=args.brand,
                    entity=args.entity,
                    date_field=date_field,
                    window_from=window_from,
                    window_to=window_to,
                    page_size=args.page_size,
                )

                cur.execute("UPDATE etl.api_pull_run SET status = 'api_success', api_record_count = %s WHERE batch_id = %s", (len(rows), batch_id))
                cur.execute("UPDATE etl.api_pull_run SET status = 's3_writing' WHERE batch_id = %s", (batch_id,))
                conn.commit()

                window_from_key = window_from.strftime("%Y%m%dT%H%M%S%z")
                window_to_key = window_to.strftime("%Y%m%dT%H%M%S%z")
                base_key = (
                    f"{s3_prefix}/source_system=provider_api/brand={args.brand}/entity={args.entity}/"
                    f"run_type={run_type}/date_field={date_field}/"
                    f"window_from={window_from_key}/window_to={window_to_key}/batch_id={batch_id}"
                )
                data_key = f"{base_key}/part-0001.jsonl.gz"
                manifest_key = f"{base_key}/manifest.json"

                manifest = {
                    "source_system": args.source_system,
                    "brand_key": args.brand,
                    "source_entity": args.entity,
                    "run_type": run_type,
                    "date_field": date_field,
                    "window_from": window_from.isoformat(),
                    "window_to": window_to.isoformat(),
                    "record_count": len(rows),
                    "api_success": True,
                    "pagination_complete": pagination_complete,
                    "is_complete_snapshot": complete_snapshot,
                    "external_batch_id": external_batch_id,
                    "internal_batch_id": batch_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

                s3_bucket, data_key, manifest_key = write_file(
                    rows=rows,
                    manifest=manifest,
                    s3_bucket=s3_bucket,
                    data_key=data_key,
                    manifest_key=manifest_key,
                    local_s3_dir=args.local_s3_dir,
                    aws_region=args.aws_region,
                )

                mark_s3_written(
                    cur,
                    batch_id=batch_id,
                    s3_bucket=s3_bucket,
                    s3_key=data_key,
                    manifest_key=manifest_key,
                    manifest=manifest,
                    api_record_count=len(rows),
                    pagination_complete=pagination_complete,
                )
                update_watermark(
                    cur,
                    source_system=args.source_system,
                    brand=args.brand,
                    entity=args.entity,
                    window_from=window_from,
                    window_to=window_to,
                    batch_id=batch_id,
                    s3_bucket=s3_bucket,
                    s3_key=data_key,
                )
                conn.commit()

                print(json.dumps({
                    "success": True,
                    "batch_id": batch_id,
                    "run_type": run_type,
                    "record_count": len(rows),
                    "s3_bucket": s3_bucket,
                    "s3_key": data_key,
                    "manifest_s3_key": manifest_key,
                    "local_s3_dir": args.local_s3_dir,
                }, indent=2))
                return 0

        except Exception as exc:
            conn.rollback()
            with conn.cursor() as cur:
                try:
                    if batch_id:
                        update_status(cur, batch_id, "failed", "failed", str(exc))
                    # Use best-known window values if available.
                    wf = parse_dt(args.window_from) if args.window_from else datetime.now(timezone.utc) - timedelta(minutes=5)
                    wt = parse_dt(args.window_to) if args.window_to else datetime.now(timezone.utc)
                    log_failure(cur, source_system=args.source_system, brand=args.brand, entity=args.entity,
                                window_from=wf, window_to=wt, batch_id=batch_id, error_message=str(exc))
                    conn.commit()
                except Exception:
                    conn.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
