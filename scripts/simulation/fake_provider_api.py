#!/usr/bin/env python3
"""
Fake Provider API for Nexus V2 POC simulation.

This script acts like a provider API. It returns JSON records filtered by a date field.
It also allows a simple source-side delete simulation.

No external dependencies are required.

Example:
  python scripts/simulation/fake_provider_api.py --port 8088 --data-file /tmp/provider_records.json

Endpoints:
  GET  /records?brand=inplay&entity=gameTx&date_field=createdDate&from=2026-05-11T10:00:00+08:00&to=2026-05-11T11:00:00+08:00&page=1&page_size=100
  POST /delete?externalId=abc123
  POST /reset
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_ROWS = [
    {
        "brand": "inplay",
        "entity": "gameTx",
        "platform": "platformA",
        "externalId": f"TX{i:03d}",
        "username": f"player{i:03d}",
        "createdDate": "2026-05-11T10:15:00+08:00",
        "settledDate": "2026-05-11T10:30:00+08:00",
        "betAmount": 100 + i,
        "payout": 50 + i,
        "status": "SETTLED",
    }
    for i in range(1, 11)
]


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_ROWS, indent=2), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def save_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    data_file: Path

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/records":
            self._json(404, {"error": "not_found"})
            return

        q = parse_qs(parsed.query)
        brand = q.get("brand", [""])[0]
        entity = q.get("entity", [""])[0]
        date_field = q.get("date_field", ["createdDate"])[0]
        from_ts = q.get("from", [None])[0]
        to_ts = q.get("to", [None])[0]
        page = int(q.get("page", ["1"])[0])
        page_size = int(q.get("page_size", ["100"])[0])

        if not from_ts or not to_ts:
            self._json(400, {"error": "from and to are required"})
            return

        start = parse_dt(from_ts)
        end = parse_dt(to_ts)
        rows = load_rows(self.data_file)

        filtered = []
        for row in rows:
            if row.get("brand") != brand or row.get("entity") != entity:
                continue
            if date_field not in row:
                continue
            row_dt = parse_dt(row[date_field])
            if start <= row_dt < end:
                filtered.append(row)

        total = len(filtered)
        total_pages = max(1, math.ceil(total / page_size))
        begin = (page - 1) * page_size
        end_idx = begin + page_size
        page_rows = filtered[begin:end_idx]

        self._json(200, {
            "api_success": True,
            "pagination_complete": page >= total_pages,
            "page": page,
            "page_size": page_size,
            "total_records": total,
            "total_pages": total_pages,
            "records": page_rows,
            "server_time": datetime.now(timezone.utc).isoformat(),
        })

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)

        if parsed.path == "/delete":
            external_id = q.get("externalId", [None])[0]
            if not external_id:
                self._json(400, {"error": "externalId is required"})
                return
            rows = load_rows(self.data_file)
            before = len(rows)
            rows = [r for r in rows if r.get("externalId") != external_id]
            save_rows(self.data_file, rows)
            self._json(200, {"deleted": before - len(rows), "remaining": len(rows)})
            return

        if parsed.path == "/reset":
            save_rows(self.data_file, DEFAULT_ROWS)
            self._json(200, {"reset": True, "record_count": len(DEFAULT_ROWS)})
            return

        self._json(404, {"error": "not_found"})

    def log_message(self, fmt: str, *args) -> None:
        print("fake_provider_api:", fmt % args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--data-file", default="/tmp/nexus_fake_provider_records.json")
    args = ap.parse_args()

    Handler.data_file = Path(args.data_file)
    load_rows(Handler.data_file)
    server = HTTPServer((args.host, args.port), Handler)
    print(f"Fake Provider API listening on http://{args.host}:{args.port}")
    print(f"Data file: {Handler.data_file}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
