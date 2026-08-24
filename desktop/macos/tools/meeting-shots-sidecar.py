#!/usr/bin/env python3
"""
meeting-shots-sidecar.py — the screenshot adjudicator, standing in for the backend route.

WHAT THIS IS
    A loopback HTTP service on 127.0.0.1:10247 implementing the adjudication half of the
    meeting-note screenshots design. The macOS app sends candidate frames; this decodes
    their pixels out of the local Rewind video chunks, sends them to gemini-flash-lite, and
    returns per-frame verdicts plus a banner choice.

WHAT THIS IS NOT
    The shipping design. There, adjudication is a backend route that canonicalises the
    bytes, judges those exact bytes, and mints a one-use signed approval that the storage
    layer requires; the client can never manufacture a publish decision. Here nothing is
    stored anywhere at all -- no bucket, no Firestore, no upload -- so the trust question
    does not arise. The wire contract is deliberately the same so the app's half does not
    have to be rewritten when the real route lands.

    Two properties of the real design ARE preserved, because they are what the prototype is
    for testing:
      - the judge sees the frame, and only frames the on-device filter already admitted;
      - the app cannot publish anything the judge did not name.

PRIVACY
    Frames are decoded to a temp file, base64'd into one Vertex request, and deleted. They
    are never written anywhere persistent and never leave this machine except as that
    request. Nothing is logged but ids, decisions and timings.

RUN
    python3 tools/meeting-shots-sidecar.py
    OMI_FORCE_MEETING_NOTE_SCREENSHOTS=1 OMI_APP_NAME=omi-meeting-shots ./run.sh --yolo
    (needs: gcloud ADC for project based-hardware, and ffmpeg on PATH)
"""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = int(os.environ.get("OMI_MEETING_SHOTS_PORT", "10247"))
PROJECT = os.environ.get("OMI_VERTEX_PROJECT", "based-hardware")
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash-lite"
ENDPOINT = (
    f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
    f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
)
MAX_PX = 1024

# Where the app keeps its chunks. Resolved per request from the bundle the app reports, with
# the two real installs as the default search path.
VIDEO_ROOTS = [
    Path(os.path.expanduser(p))
    for p in (
        os.environ.get("OMI_MEETING_SHOTS_VIDEO_ROOT", ""),
        "~/Library/Application Support/Omi Beta/users",
        "~/Library/Application Support/Omi/users",
    )
    if p
]

JUDGE_SYSTEM = """You decide which screenshots taken during a meeting may be shown inside \
that meeting's notes, and which single frame best represents the meeting.

This is a privacy decision before it is an editorial one. A frame you publish will be stored \
and shown to the user, and may be visible to anyone they share the note with.

Set sensitivity="sensitive" AND decision="reject" for any frame showing: visible credentials \
or a login/auth screen, a password manager, private messages or DMs, an email inbox, banking \
or payment details, medical information, or personal content unrelated to the meeting.

Meeting join credentials count as credentials. A dial-in phone number, a meeting PIN or \
passcode, or a join URL is a way in to the call and must be rejected even though it appears \
inside an ordinary conferencing window. Measured: a Google Meet frame showing a dial-in number \
and PIN was previously judged "clean" and chosen as the note's banner.

Publish a frame only if it would genuinely help someone remember or understand THIS meeting: \
the artifact discussed, the thing demoed, the diagram, the data, the document. Prefer a varied \
set over several views of the same thing. Publishing nothing is a valid and correct answer.

Choose banner_id as the one frame that best represents the meeting at a glance. It will be \
shown SMALL, as an inset in a designed header -- not stretched across the top -- so favour a \
frame with a recognisable, legible subject over a dense wall of text. If no frame is suitable, \
return banner_id = 0.

Captions are one short factual line. No marketing voice."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdicts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER"},
                    "decision": {"type": "STRING", "enum": ["publish", "reject"]},
                    "sensitivity": {"type": "STRING", "enum": ["clean", "sensitive"]},
                    "caption": {"type": "STRING"},
                    "labels": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "reason": {"type": "STRING"},
                },
                "required": ["id", "decision", "sensitivity", "caption", "labels", "reason"],
            },
        },
        "banner_id": {"type": "INTEGER"},
        "banner_reason": {"type": "STRING"},
    },
    "required": ["verdicts", "banner_id", "banner_reason"],
}

_token = {"value": None, "at": 0.0}


def access_token():
    if time.time() - _token["at"] > 1800:
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"], capture_output=True, text=True
        )
        if out.returncode != 0:
            raise RuntimeError("gcloud auth print-access-token failed; run `gcloud auth login`")
        _token["value"] = out.stdout.strip()
        _token["at"] = time.time()
    return _token["value"]


def resolve_chunk(rel_path, video_root=None):
    """Find a chunk. The client's own resolved Videos directory wins over any guess."""
    if not rel_path:
        return None
    if video_root:
        candidate = Path(video_root) / rel_path
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    for root in VIDEO_ROOTS:
        if not root.exists():
            continue
        # root is .../users -- search each uid's Videos dir
        for videos in list(root.glob("*/Videos")) + [root]:
            candidate = videos / rel_path
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
    return None


def decode_frame(chunk_path, frame_offset):
    """One frame out of an H.264 chunk, downsampled, as JPEG bytes. None when unrecoverable."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        out = Path(tmp.name)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(chunk_path),
             "-vf", f"select=eq(n\\,{int(frame_offset)}),scale='min({MAX_PX},iw)':-2",
             "-frames:v", "1", "-q:v", "6", "-y", str(out)],
            capture_output=True, check=False,
        )
        if out.exists() and out.stat().st_size > 0:
            return out.read_bytes()
        return None
    finally:
        out.unlink(missing_ok=True)


def adjudicate(payload):
    candidates = payload.get("candidates", [])
    title = payload.get("meeting_title") or "this meeting"
    cap = int(payload.get("max_publish", 6))
    video_root = payload.get("video_root")

    parts = [{"text": f"Meeting: {title!r}\n\nCandidate frames follow, each labelled with its id. "
                      f"Publish at most {cap}."}]
    seen, unrecoverable = [], []
    for c in candidates:
        chunk = resolve_chunk(c.get("video_chunk_path"), video_root)
        if not chunk:
            unrecoverable.append(c["id"])
            continue
        jpeg = decode_frame(chunk, c.get("frame_offset", 0))
        if not jpeg:
            unrecoverable.append(c["id"])
            continue
        seen.append(c["id"])
        parts.append({"text": f"\n--- id={c['id']} app={c.get('app_name','')}"})
        parts.append({"inlineData": {"mimeType": "image/jpeg",
                                     "data": base64.b64encode(jpeg).decode()}})

    if not seen:
        print(f"  WARNING: none of {len(candidates)} candidate(s) could be decoded — "
              f"video_root={video_root!r}. No judge call was made; this is a path problem, "
              f"not a rejection.", flush=True)
        return {"verdicts": [], "banner_id": 0,
                "banner_reason": "no candidate frame could be decoded",
                "unrecoverable": unrecoverable}

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "systemInstruction": {"parts": [{"text": JUDGE_SYSTEM}]},
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": 0},
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "temperature": 0,
        },
    }
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", ENDPOINT,
         "-H", f"Authorization: Bearer {access_token()}",
         "-H", "Content-Type: application/json", "--data-binary", "@-"],
        input=json.dumps(body), capture_output=True, text=True,
    )
    response = json.loads(result.stdout)
    if "candidates" not in response:
        raise RuntimeError(f"vertex: {json.dumps(response)[:300]}")

    text = "".join(p.get("text", "") for p in response["candidates"][0]["content"]["parts"])
    out = json.loads(text)
    usage = response.get("usageMetadata", {})
    out["unrecoverable"] = unrecoverable
    out["usage"] = {
        "input": usage.get("promptTokenCount", 0),
        "output": usage.get("candidatesTokenCount", 0),
        "cost_usd": round(usage.get("promptTokenCount", 0) * 1e-7
                          + usage.get("candidatesTokenCount", 0) * 4e-7, 6),
    }
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # the default logger prints the whole request line; we log deliberately below

    def do_POST(self):
        started = time.time()
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            result = adjudicate(payload)
            published = [v["id"] for v in result.get("verdicts", [])
                         if v.get("decision") == "publish"]
            print(f"  adjudicated {len(payload.get('candidates', []))} candidate(s) -> "
                  f"{len(published)} publish, banner={result.get('banner_id')}, "
                  f"{result.get('usage', {}).get('cost_usd', 0)} USD, "
                  f"{time.time() - started:.1f}s", flush=True)
            self._send(200, result)
        except Exception as exc:  # a sidecar that dies on one bad request is useless to test with
            print(f"  ERROR: {exc}", flush=True)
            self._send(500, {"error": str(exc)})

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    if not any(r.exists() for r in VIDEO_ROOTS):
        print("WARNING: no Rewind Videos directory found; every frame will be unrecoverable.")
    print(f"meeting-shots adjudicator on http://127.0.0.1:{PORT}")
    print(f"  model   {MODEL} in {PROJECT}/{LOCATION}")
    print("  nothing is uploaded or stored; frames are decoded, judged, and discarded.")
    try:
        access_token()
        print("  gcloud credentials OK")
    except Exception as exc:
        print(f"  WARNING: {exc}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
