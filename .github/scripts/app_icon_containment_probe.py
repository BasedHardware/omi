#!/usr/bin/env python3
"""Make one synthetic request to the public app-icon route."""

import http.client
import json
from pathlib import Path
import sys


def probe(token_file: Path) -> tuple[int | None, str]:
    status = None
    try:
        token = token_file.read_text(encoding="ascii").strip()
        if not token:
            return None, "token_unavailable"
        # HTTPSConnection sends a single request without following redirects.
        connection = http.client.HTTPSConnection("api.omi.me", timeout=15)
        try:
            connection.request(
                "POST",
                "/v1/app/generate-icon",
                body=json.dumps(
                    {"name": "Release probe", "description": "A plain blue square", "category": "other"}
                ),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with connection.getresponse() as response:
                status = response.status
                if status != 424:
                    return status, "unexpected_status"
                body = response.read(4097)
        finally:
            connection.close()
    except (OSError, ValueError, http.client.HTTPException):
        return status, "response_unavailable"

    if len(body) <= 4096:
        try:
            detail = json.loads(body).get("detail")
            if isinstance(detail, dict) and detail.get("code") == "icon_generation_disabled":
                return status, "icon_generation_disabled"
        except (AttributeError, ValueError, RecursionError):
            pass
    return status, "unexpected_response"


if __name__ == "__main__":
    status, outcome = probe(Path(sys.argv[1]))
    print(f"http_status={status if status is not None else 'none'} outcome={outcome}")
