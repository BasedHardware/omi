#!/usr/bin/env python3
"""Create Typesense collections for local development.

Idempotent — safe to run multiple times.
"""

import json
import sys
import urllib.request
import urllib.error

TYPESENSE_HOST = "http://localhost:8108"
TYPESENSE_API_KEY = "local-dev-key"

SCHEMA = {
    "name": "conversations",
    "fields": [
        {"name": "structured", "type": "object"},
        {"name": "structured.category", "type": "string", "facet": True},
        {"name": "created_at", "type": "int64"},
        {"name": "started_at", "type": "int64", "optional": True},
        {"name": "finished_at", "type": "int64", "optional": True},
        {"name": "userId", "type": "string"},
        {"name": "discarded", "type": "bool", "optional": True},
        {"name": "geolocation", "type": "object", "optional": True},
    ],
    "default_sorting_field": "created_at",
    "enable_nested_fields": True,
}


def create_collection():
    url = f"{TYPESENSE_HOST}/collections"
    data = json.dumps(SCHEMA).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
        },
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req)
        print(f"Created collection 'conversations': {resp.status}")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print("Collection 'conversations' already exists — skipping.")
        else:
            body = e.read().decode()
            print(f"Error creating collection: {e.code} {body}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    create_collection()
