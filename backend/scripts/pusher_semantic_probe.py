#!/usr/bin/env python3
"""Exercise deployed dev listen -> Pusher -> durable finalization -> read-back.

The probe uses the repository's versioned LibriSpeech release fixture and the
existing short-lived Firebase release-probe identity. It never substitutes a
provider, writes a PASS without terminal read-back, or includes token,
transcript, UID, or endpoint data in its receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import websockets

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "backend/testing/release_fixtures/transcription-release-probe.wav"
FIXTURE_MANIFEST_PATH = ROOT / "backend/testing/release_fixtures/transcription-release-probe.json"
MAX_TOKEN_CHARS = 8192
MAX_HTTP_BYTES = 512 * 1024
CHUNK_MILLISECONDS = 100
SYNTHETIC_UID_CLASS = "firebase_release_probe"
FIXTURE_CODEC = "pcm16"


class ProbeError(RuntimeError):
    """A bounded probe stage failed without retaining response or transcript data."""

    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


@dataclass(frozen=True)
class Fixture:
    pcm: bytes
    sample_rate: int
    expected_phrase: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_token(path: Path) -> str:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or stat.S_IMODE(file_stat.st_mode) & 0o077:
            raise ProbeError("token_permissions")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            token = handle.read().strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise ProbeError("token_read") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise ProbeError("token_read")
    return token


def _normalize(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join("".join(character.casefold() if character.isalnum() else " " for character in value).split())


def load_fixture() -> Fixture:
    try:
        manifest = json.loads(FIXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))
        raw = FIXTURE_PATH.read_bytes()
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("fixture_filename") != FIXTURE_PATH.name
            or hashlib.sha256(raw).hexdigest() != manifest.get("sha256")
        ):
            raise ProbeError("fixture_contract")
        expected_phrase = _normalize(manifest.get("expected_transcript"))
        with wave.open(str(FIXTURE_PATH), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                raise ProbeError("fixture_contract")
            sample_rate = handle.getframerate()
            pcm = handle.readframes(handle.getnframes())
        if not expected_phrase or not pcm:
            raise ProbeError("fixture_contract")
    except (OSError, ValueError, json.JSONDecodeError, wave.Error) as exc:
        raise ProbeError("fixture_contract") from exc
    return Fixture(pcm=pcm, sample_rate=sample_rate, expected_phrase=expected_phrase)


async def _receive_json(websocket: Any, deadline: float) -> Any:
    while time.monotonic() < deadline:
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=min(5.0, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            continue
        if not isinstance(message, str) or message == "ping":
            continue
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            continue
    raise ProbeError("listen_timeout")


async def _listen_sample(
    base_url: str, token: str, fixture: Fixture, conversation_id: str, *, allow_local_http: bool = False
) -> None:
    parsed = urllib.parse.urlparse(base_url)
    local_http = allow_local_http and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if (parsed.scheme != "https" and not local_http) or not parsed.netloc or parsed.path not in {"", "/"}:
        raise ProbeError("api_url")
    query = urllib.parse.urlencode(
        {
            "language": "en",
            "sample_rate": fixture.sample_rate,
            # The versioned fixture is signed 16-bit PCM. Declaring pcm8 would
            # make the receiver bias and widen each byte independently,
            # corrupting the audio while still producing a valid WebSocket.
            "codec": FIXTURE_CODEC,
            "channels": 1,
            "include_speech_profile": "false",
            "source": "desktop",
            "stt_service": "parakeet",
            "client_conversation_id": conversation_id,
        }
    )
    websocket_url = f"{'ws' if local_http else 'wss'}://{parsed.netloc}/v4/listen?{query}"
    transcripts: list[str] = []
    session_bound = False
    ready = False
    async with websockets.connect(
        websocket_url,
        extra_headers={"Authorization": f"Bearer {token}", "X-App-Platform": "desktop"},
        max_size=10 * 1024 * 1024,
        open_timeout=30,
        ping_interval=20,
        ping_timeout=20,
    ) as websocket:
        deadline = time.monotonic() + 60
        while not (session_bound and ready):
            payload = await _receive_json(websocket, deadline)
            if isinstance(payload, dict) and payload.get("type") == "conversation_session":
                session_bound = payload.get("conversation_id") == conversation_id
            if (
                isinstance(payload, dict)
                and payload.get("type") == "service_status"
                and payload.get("status") == "ready"
            ):
                ready = True
        chunk_bytes = fixture.sample_rate * 2 * CHUNK_MILLISECONDS // 1000

        async def receive_transcripts() -> None:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    payload = await _receive_json(websocket, deadline)
                except ProbeError:
                    return
                segments = (
                    payload
                    if isinstance(payload, list)
                    else payload.get("segments") if isinstance(payload, dict) else None
                )
                if isinstance(segments, list):
                    transcripts.extend(
                        str(segment.get("text", ""))
                        for segment in segments
                        if isinstance(segment, dict) and segment.get("text")
                    )

        receiver = asyncio.create_task(receive_transcripts())
        for offset in range(0, len(fixture.pcm), chunk_bytes):
            chunk = fixture.pcm[offset : offset + chunk_bytes]
            if len(chunk) != chunk_bytes:
                break
            await websocket.send(chunk)
            await asyncio.sleep(CHUNK_MILLISECONDS / 1000)
        await asyncio.sleep(5)
        receiver.cancel()
        try:
            await receiver
        except asyncio.CancelledError:
            pass
        combined = _normalize(" ".join(transcripts))
        if fixture.expected_phrase not in combined:
            raise ProbeError("transcript_mismatch")
        await websocket.close(code=1000, reason="release_probe_complete")


def _http_json(url: str, token: str) -> tuple[int, dict[str, Any] | None]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(MAX_HTTP_BYTES + 1)
            status = int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code), None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return 0, None
    if len(body) > MAX_HTTP_BYTES:
        return status, None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None
    return status, payload if isinstance(payload, dict) else None


async def _terminal_readback(base_url: str, token: str, conversation_id: str, timeout_seconds: int) -> None:
    quoted_id = urllib.parse.quote(conversation_id, safe="")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status, payload = await asyncio.to_thread(
            _http_json, f"{base_url}/v1/conversations/{quoted_id}/finalization", token
        )
        if status == 200 and payload is not None and payload.get("terminal") is True:
            if (
                payload.get("status") != "completed"
                or payload.get("terminal_outcome") != "success"
                or payload.get("fanout_status") != "completed"
            ):
                raise ProbeError("terminal_failure")
            break
        if status not in {0, 200, 404}:
            raise ProbeError("finalization_read")
        await asyncio.sleep(5)
    else:
        raise ProbeError("finalization_timeout")
    status, conversation = await asyncio.to_thread(_http_json, f"{base_url}/v1/conversations/{quoted_id}", token)
    if (
        status != 200
        or conversation is None
        or conversation.get("id") != conversation_id
        or conversation.get("status") != "completed"
        or not conversation.get("transcript_segments")
    ):
        raise ProbeError("consumer_readback")


async def _observe_candidate_pusher(
    deployment_receipt: dict[str, Any], *, conversation_id: str, project: str, namespace: str
) -> int:
    live_identity = (
        deployment_receipt.get("live_identity") if isinstance(deployment_receipt.get("live_identity"), dict) else {}
    )
    candidate_pods = {
        pod.get("name")
        for pod in live_identity.get("pods", [])
        if isinstance(pod, dict) and isinstance(pod.get("name"), str)
    }
    if not candidate_pods or live_identity.get("namespace") != namespace:
        raise ProbeError("producer_identity")
    started = datetime.now(timezone.utc).timestamp() - 15 * 60
    query = (
        'resource.type="k8s_container" '
        f'resource.labels.namespace_name="{namespace}" '
        'resource.labels.container_name="pusher" '
        f'timestamp>="{datetime.fromtimestamp(started, timezone.utc).isoformat()}" '
        # Header 103 only proves that a Pusher socket observed the session.
        # Header 104 is the candidate-owned durable-finalization handoff.
        f'textPayload:"Pusher received process_conversation request: {conversation_id}"'
    )
    for _ in range(12):
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "gcloud",
                "logging",
                "read",
                query,
                f"--project={project}",
                "--limit=20",
                "--format=value(resource.labels.pod_name)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            observed_pods = {line.strip() for line in result.stdout.splitlines() if line.strip()}
            attributed_pods = observed_pods & candidate_pods
            if len(attributed_pods) == 1:
                return 1
            if len(attributed_pods) > 1:
                raise ProbeError("producer_attribution_ambiguous")
        await asyncio.sleep(5)
    raise ProbeError("producer_observation")


def _receipt(
    *,
    status: str,
    evidence_id: str,
    deployment_receipt: dict[str, Any],
    deployment_receipt_sha256: str,
    started_at: str,
    ended_at: str,
    candidate_pod_count: int,
    failure_stage: str | None,
) -> dict[str, Any]:
    image = deployment_receipt.get("image") if isinstance(deployment_receipt.get("image"), dict) else {}
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "evidence_id": evidence_id,
        "candidate": {
            "source_sha": deployment_receipt.get("source_sha"),
            "image_digest": image.get("digest"),
            "deployment_receipt_sha256": deployment_receipt_sha256,
        },
        "window": {"started_at": started_at, "ended_at": ended_at, "closed_at": _now()},
        "samples": {
            "attempted": 1,
            "succeeded": 1 if status == "PASS" else 0,
            "failed": 0 if status == "PASS" else 1,
        },
        "synthetic_uid_class": SYNTHETIC_UID_CLASS,
        "producer_observation": {
            "status": "PASS" if status == "PASS" else "FAIL",
            "candidate_pod_count": candidate_pod_count,
        },
        "consumer_readback": {"status": "PASS" if status == "PASS" else "FAIL"},
    }
    if failure_stage is not None:
        receipt["failure_stage"] = failure_stage
    return receipt


async def run_probe(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    started_at = _now()
    evidence_id = f"pusher-dev-{args.run_id}-{uuid.uuid4().hex}"
    failure_stage: str | None = None
    candidate_pod_count = 0
    try:
        token = _read_token(args.bearer_token_file)
        fixture = load_fixture()
        deployment_receipt = json.loads(args.deployment_receipt.read_text(encoding="utf-8"))
        if not isinstance(deployment_receipt, dict):
            raise ProbeError("deployment_receipt")
        deployment_receipt_sha256 = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(deployment_receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )
        conversation_id = str(uuid.uuid4())
        await _listen_sample(
            args.api_url.rstrip("/"), token, fixture, conversation_id, allow_local_http=args.allow_local_http
        )
        await _terminal_readback(args.api_url.rstrip("/"), token, conversation_id, args.finalization_timeout_seconds)
        candidate_pod_count = await _observe_candidate_pusher(
            deployment_receipt,
            conversation_id=conversation_id,
            project=args.project,
            namespace=args.namespace,
        )
    except (OSError, json.JSONDecodeError, ProbeError) as error:
        failure_stage = error.stage if isinstance(error, ProbeError) else "deployment_receipt"
        deployment_receipt = locals().get("deployment_receipt", {})
        deployment_receipt_sha256 = locals().get("deployment_receipt_sha256", "")
    finally:
        if "token" in locals():
            token = ""
    ended_at = _now()
    passed = failure_stage is None
    return (
        _receipt(
            status="PASS" if passed else "FAIL",
            evidence_id=evidence_id,
            deployment_receipt=deployment_receipt,
            deployment_receipt_sha256=deployment_receipt_sha256,
            started_at=started_at,
            ended_at=ended_at,
            candidate_pod_count=candidate_pod_count,
            failure_stage=failure_stage,
        ),
        passed,
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--allow-local-http", action="store_true")
    parser.add_argument("--bearer-token-file", type=Path, required=True)
    parser.add_argument("--deployment-receipt", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    # Keep all authenticated read-back inside the existing five-minute probe
    # token lifetime even after WebSocket setup and real-time audio streaming.
    parser.add_argument("--finalization-timeout-seconds", type=int, default=180)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or os.sys.argv[1:])
    receipt, passed = asyncio.run(run_probe(args))
    args.output.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Pusher semantic probe status={receipt['status']} evidence_id={receipt['evidence_id']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
