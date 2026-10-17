#!/usr/bin/env python3
"""Index a user's conversations from the LOCAL Firestore emulator into the LOCAL Typesense.

Production fills Typesense through the Firestore -> Typesense sync extension, which the upstream
dev harness does not run, so the agent's search_conversations_tool finds nothing locally. This does
the same sync once: the fields the backend searches and filters on (userId, discarded, created_at,
started_at, finished_at, structured.*). Pinecone has no local stand-in; semantic search stays empty.

Usage: index_conversations_typesense.py [--uid alice | --all] [--watch SECONDS] [--emulator 127.0.0.1:8085]
       [--project demo-omi-local] [--typesense 127.0.0.1:8108]
--all indexes every user in the emulator; --watch repeats, so new recordings become searchable.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

TYPESENSE_KEY = "local-typesense-api-key-not-real"  # dev harness constant (dev_harness/config.py)
SCHEMA = {
    "name": "conversations",
    "enable_nested_fields": True,
    "fields": [
        {"name": "userId", "type": "string", "facet": True},
        {"name": "discarded", "type": "bool"},
        {"name": "created_at", "type": "int64"},
        {"name": "started_at", "type": "int64", "optional": True},
        {"name": "finished_at", "type": "int64", "optional": True},
        {"name": "structured.title", "type": "string", "optional": True},
        {"name": "structured.overview", "type": "string", "optional": True},
        {"name": "structured.emoji", "type": "string", "optional": True},
        {"name": "structured.category", "type": "string", "optional": True},
    ],
    "default_sorting_field": "created_at",
}


def local_only(host: str) -> bool:
    return host.startswith("127.0.0.1") or host.startswith("localhost")


def decode(value: dict):
    kind, raw = next(iter(value.items()))
    if kind == "mapValue":
        return {k: decode(v) for k, v in raw.get("fields", {}).items()}
    if kind == "arrayValue":
        return [decode(v) for v in raw.get("values", [])]
    if kind == "integerValue":
        return int(raw)
    if kind == "timestampValue":
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    return raw


def typesense(host: str, method: str, path: str, body: bytes | None = None, content_type="application/json"):
    request = urllib.request.Request(f"http://{host}{path}", data=body, method=method,
                                     headers={"X-TYPESENSE-API-KEY": TYPESENSE_KEY, "Content-Type": content_type})
    with urllib.request.urlopen(request) as response:
        return response.read().decode()


def index_user(args, uid: str) -> int:
    url = (f"http://{args.emulator}/v1/projects/{args.project}/databases/(default)/documents/"
           f"users/{uid}/conversations?pageSize=500")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer owner"})
    with urllib.request.urlopen(request) as response:
        documents = json.load(response).get("documents", [])

    lines = []
    for document in documents:
        fields = {k: decode(v) for k, v in document.get("fields", {}).items()}
        structured = fields.get("structured") or {}
        created = fields.get("created_at") or fields.get("started_at")
        if not isinstance(created, int):
            continue
        lines.append(json.dumps({
            "id": document["name"].rsplit("/", 1)[-1],
            "userId": uid,
            "discarded": bool(fields.get("discarded", False)),
            "created_at": created,
            "started_at": fields.get("started_at") if isinstance(fields.get("started_at"), int) else created,
            "finished_at": fields.get("finished_at") if isinstance(fields.get("finished_at"), int) else created,
            "structured": {k: structured.get(k, "") for k in ("title", "overview", "emoji", "category")},
        }))
    if not lines:
        return 0
    result = typesense(args.typesense, "POST", "/collections/conversations/documents/import?action=upsert",
                       "\n".join(lines).encode(), content_type="text/plain")
    failed = [line for line in result.splitlines() if '"success":true' not in line]
    if not args.watch:
        print(f"indexed {len(lines) - len(failed)}/{len(lines)} conversations for {uid}")
    for line in failed:
        print(line, file=sys.stderr)
    return 1 if failed else 0


def all_users(args) -> list[str]:
    url = (f"http://{args.emulator}/v1/projects/{args.project}/databases/(default)/documents/"
           f"users?pageSize=500&mask.fieldPaths=uid")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer owner"})
    with urllib.request.urlopen(request) as response:
        return [d["name"].rsplit("/", 1)[-1] for d in json.load(response).get("documents", [])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", default="alice")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--watch", type=float)
    parser.add_argument("--emulator", default="127.0.0.1:8085")
    parser.add_argument("--project", default="demo-omi-local")
    parser.add_argument("--typesense", default="127.0.0.1:8108")
    args = parser.parse_args()
    if not (local_only(args.emulator) and local_only(args.typesense)):
        print("refusing: only the local emulator and Typesense are allowed", file=sys.stderr)
        return 2
    try:
        typesense(args.typesense, "POST", "/collections", json.dumps(SCHEMA).encode())
    except urllib.error.HTTPError as error:
        if error.code != 409:  # 409: the collection exists already
            raise
    while True:
        try:
            failures = sum(index_user(args, uid) for uid in (all_users(args) if args.all else [args.uid]))
        except (urllib.error.URLError, OSError) as error:
            if not args.watch:
                raise
            print(f"index pass failed: {error}", file=sys.stderr)
            failures = 0
        if not args.watch:
            return 1 if failures else 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
