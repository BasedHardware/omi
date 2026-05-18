#!/usr/bin/env python3
"""Import a transcript fixture into the Omi local backend MVP."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8765"


def request_json(
    method: str,
    base_url: str,
    path: str,
    body: dict[str, Any] | None = None,
    ok_statuses: set[int] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    ok_statuses = ok_statuses or {200}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status not in ok_statuses:
                payload = response.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"{method} {path} failed with HTTP {response.status}: {payload}")
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace")
        if error.code in ok_statuses:
            return json.loads(payload) if payload else {}
        raise RuntimeError(f"{method} {path} failed with HTTP {error.code}: {payload}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"{method} {path} failed: {error.reason}") from error

    return json.loads(payload) if payload else {}


def load_fixture(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return load_json_fixture(json.loads(raw), path)
    return (
        {"title": path.stem.replace("_", " ").replace("-", " ").strip().title() or "Imported Transcript"},
        plain_text_segments(raw),
    )


def load_json_fixture(value: Any, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conversation: dict[str, Any] = {
        "title": path.stem.replace("_", " ").replace("-", " ").strip().title() or "Imported Transcript"
    }
    segment_values: Any = value

    if isinstance(value, dict):
        conversation = {
            key: value[key]
            for key in ("id", "session_id", "title", "overview", "started_at", "metadata")
            if key in value
        }
        segment_values = value.get("segments", value.get("transcript_segments", value.get("transcript", [])))

    if not isinstance(segment_values, list):
        raise ValueError("JSON fixture must be a list, or an object with segments/transcript_segments")

    segments = []
    for index, item in enumerate(segment_values):
        if isinstance(item, str):
            text = item.strip()
            segment = {"text": text}
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            segment = dict(item)
            segment["text"] = text
        else:
            raise ValueError(f"Segment {index} must be a string or object")

        if text:
            segment.setdefault("start_ms", index * 2_000)
            segment.setdefault("end_ms", segment["start_ms"] + 2_000)
            segment.setdefault("segment_index", index)
            segment.setdefault("source", "local_import")
            segments.append(segment)

    return conversation, segments


def plain_text_segments(raw: str) -> list[dict[str, Any]]:
    chunks = [chunk.strip() for chunk in raw.replace("\r\n", "\n").split("\n\n") if chunk.strip()]
    if not chunks:
        chunks = [line.strip() for line in raw.splitlines() if line.strip()]

    return [
        {
            "text": chunk,
            "start_ms": index * 2_000,
            "end_ms": (index + 1) * 2_000,
            "segment_index": index,
            "source": "local_import",
        }
        for index, chunk in enumerate(chunks)
    ]


def wait_for_job(base_url: str, job_id: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_job = request_json("GET", base_url, f"/v1/processing-jobs/{urllib.parse.quote(job_id)}")[
            "processing_job"
        ]
        if last_job["status"] in {"completed", "failed"}:
            return last_job
        request_json("POST", base_url, "/v1/processing-jobs/process-next")
        time.sleep(0.25)
    raise TimeoutError(f"Processing job {job_id} did not finish; last status: {last_job.get('status')}")


def default_search_query(segments: list[dict[str, Any]]) -> str:
    for segment in segments:
        words = [word.strip(".,:;!?()[]{}\"'") for word in segment["text"].split()]
        words = [word for word in words if len(word) > 3]
        if words:
            return " ".join(words[:3])
    return segments[0]["text"][:24]


def search_safe_query(raw: str) -> str:
    query = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
    query = " ".join(query.split())
    return query or raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path, help="Plain text or JSON transcript fixture")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Local daemon URL, default {DEFAULT_BASE_URL}")
    parser.add_argument("--title", help="Override the conversation title")
    parser.add_argument("--overview", help="Override the conversation overview")
    parser.add_argument("--conversation-id", help="Use a specific conversation ID")
    parser.add_argument("--session-id", help="Use a specific session ID")
    parser.add_argument("--search-query", help="Search query to verify after import")
    parser.add_argument("--wait-timeout", type=float, default=15.0, help="Seconds to wait for finalize processing")
    args = parser.parse_args()

    conversation, segments = load_fixture(args.transcript)
    if not segments:
        raise ValueError("Transcript fixture did not contain any non-empty segments")

    for key, value in (
        ("id", args.conversation_id),
        ("session_id", args.session_id),
        ("title", args.title),
        ("overview", args.overview),
    ):
        if value:
            conversation[key] = value

    request_json("GET", args.base_url, "/health")
    if "id" in conversation:
        existing = request_json(
            "GET",
            args.base_url,
            f"/v1/conversations/{urllib.parse.quote(conversation['id'])}",
            ok_statuses={200, 404},
        )
        created = existing.get("conversation")
    else:
        created = None
    if created is None:
        created = request_json("POST", args.base_url, "/v1/conversations", conversation)["conversation"]
    conversation_id = created["id"]

    for index, segment in enumerate(segments):
        payload = dict(segment)
        payload.setdefault("segment_index", index)
        request_json(
            "POST",
            args.base_url,
            f"/v1/conversations/{urllib.parse.quote(conversation_id)}/transcript-segments",
            payload,
        )

    queued_job = request_json(
        "POST",
        args.base_url,
        f"/v1/conversations/{urllib.parse.quote(conversation_id)}/finalize-transcript",
    )["processing_job"]
    completed_job = wait_for_job(args.base_url, queued_job["id"], args.wait_timeout)
    if completed_job["status"] != "completed":
        raise RuntimeError(f"Finalize processing failed for {conversation_id}: {completed_job}")

    search_query = search_safe_query(args.search_query or default_search_query(segments))
    encoded_query = urllib.parse.urlencode({"q": search_query})
    search = request_json("GET", args.base_url, f"/v1/search/conversations?{encoded_query}")
    if not any(result.get("conversation_id") == conversation_id for result in search.get("results", [])):
        raise RuntimeError(f"Search for {search_query!r} did not find imported conversation {conversation_id}")

    print(f"Imported conversation: {conversation_id}")
    print(f"Segments imported: {len(segments)}")
    print(f"Finalize job: {completed_job['id']} ({completed_job['status']})")
    print(f"Read command: curl {args.base_url.rstrip('/')}/v1/conversations/{conversation_id}")
    print(
        "Search command: "
        f"curl '{args.base_url.rstrip('/')}/v1/search/conversations?{urllib.parse.urlencode({'q': search_query})}'"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"import_transcript.py: {error}", file=sys.stderr)
        raise SystemExit(1)
