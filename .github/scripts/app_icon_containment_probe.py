#!/usr/bin/env python3
"""Probe app-icon containment through the admitted Cloud Run revision's tag."""

import hashlib
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys

BACKEND_SCRIPTS = Path(__file__).resolve().parents[2] / "backend" / "scripts"
sys.path.insert(0, str(BACKEND_SCRIPTS))
from resolve_cloud_run_tagged_url import TaggedUrlResolutionError, resolve_tagged_url
from verify_backend_release_vector import evaluate_candidate_zero_traffic

PROJECT = "based-hardware"
REGION = "us-central1"
SERVICE = "backend"
IDENTITY_ERRORS = (
    TaggedUrlResolutionError,
    subprocess.SubprocessError,
    OSError,
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
)


def describe(resource: str, name: str, fields: str) -> dict:
    result = subprocess.run(
        [
            "gcloud", "run", resource, "describe", name,
            f"--project={PROJECT}", f"--region={REGION}", f"--format=json({fields})",
        ],
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def revision_matches_dispatch(revision: str, source: str) -> bool:
    doc = describe("revisions", revision, "metadata.name,metadata.labels,spec.containers.env,status.conditions")
    metadata = doc["metadata"]
    stamps = [
        env.get("value")
        for container in doc["spec"]["containers"]
        for env in container.get("env", [])
        if env["name"] == "OMI_BACKEND_RELEASE_SHA"
    ]
    ready = [condition["status"] for condition in doc["status"]["conditions"] if condition["type"] == "Ready"]
    return (
        metadata["name"] == revision
        and metadata["labels"]["serving.knative.dev/service"] == SERVICE
        and ready == ["True"]
        and stamps == [source]
    )


def candidate_binding(revision: str) -> tuple[str, str]:
    tag = "icon-" + hashlib.sha256(revision.encode("ascii")).hexdigest()[:24]
    doc = describe("services", SERVICE, "metadata.name,metadata.resourceVersion,metadata.generation,spec.traffic,status")
    metadata, spec, status = doc["metadata"], doc["spec"], doc["status"]
    resource_version = metadata["resourceVersion"]
    if (
        metadata["name"] != SERVICE
        or not isinstance(resource_version, str)
        or not resource_version
        or type(metadata["generation"]) is not int
        or metadata["generation"] < 1
        or str(status["observedGeneration"]) != str(metadata["generation"])
        or not spec["traffic"]
        or evaluate_candidate_zero_traffic(SERVICE, revision, status, spec)
    ):
        raise TaggedUrlResolutionError("invalid candidate traffic state")

    for traffic in (spec["traffic"], status["traffic"]):
        targets = [target for target in traffic if target.get("tag") == tag]
        if (
            len(targets) != 1
            or targets[0].get("latestRevision", False) is not False
            or targets[0].get("revisionName") != revision
        ):
            raise TaggedUrlResolutionError("candidate tag is missing or mismatched")

    url = resolve_tagged_url(doc, revision=revision, tag=tag)
    service_url = status["url"]
    # Keep the bearer on the Cloud Run endpoint returned for this production
    # service. Refuse caller URLs and the shared service hostname.
    if (
        not re.fullmatch(r"https://backend-[a-z0-9-]+(?:\.[a-z0-9-]+)?\.run\.app", service_url)
        or url != f"https://{tag}---{service_url.removeprefix('https://')}"
    ):
        raise TaggedUrlResolutionError("unexpected candidate endpoint")
    return url.removeprefix("https://"), resource_version


def probe(token_file: Path, host: str) -> tuple[int | None, str]:
    status = None
    try:
        token = token_file.read_text(encoding="ascii").strip()
        if not token:
            return None, "token_unavailable"
        # HTTPSConnection sends a single request without following redirects.
        connection = http.client.HTTPSConnection(host, timeout=15)
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


def run_probe(token_file: Path, revision: str, source: str) -> tuple[int | None, str]:
    if not (
        re.fullmatch(r"backend-[a-z0-9](?:[a-z0-9-]{0,53}[a-z0-9])?", revision)
        and re.fullmatch(r"[0-9a-f]{40}", source)
        and source != "0" * 40
    ):
        return None, "candidate_input_invalid"

    try:
        if not revision_matches_dispatch(revision, source):
            return None, "candidate_identity_unverified"
        binding = candidate_binding(revision)
    except IDENTITY_ERRORS:
        return None, "candidate_identity_unverified"

    try:
        subprocess.run(
            [
                sys.executable, "-I", str(BACKEND_SCRIPTS / "firebase_release_probe_token.py"),
                "--secret-project", PROJECT, "--firebase-project", PROJECT, "--token-output", str(token_file),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=90,
        )
    except (subprocess.SubprocessError, OSError):
        return None, "token_mint_failed"

    status, outcome = probe(token_file, binding[0])
    if outcome == "icon_generation_disabled":
        try:
            # Credit a typed 424 only if the exact route remained bound across
            # the request. The readback also catches an out-of-band tag writer.
            if candidate_binding(revision) == binding:
                return status, outcome
        except IDENTITY_ERRORS:
            pass
        return status, "candidate_identity_unverified"
    return status, outcome


if __name__ == "__main__":
    status, outcome = run_probe(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    print(f"http_status={status if status is not None else 'none'} outcome={outcome}")
