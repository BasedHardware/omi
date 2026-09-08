#!/usr/bin/env python3
"""Idempotent ensure for the development-only parity-pack GCS bucket.

Creates a private bucket and least-privilege bindings used by backend-listen
dogfood capture export. Safe to re-run. Never touches prod.

Names are fixed so chart values, IAM, and download commands stay aligned:
  bucket: based-hardware-dev-omi-parity-pack-v0
  prefix: parity-pack/v0
  GSA:    dev-omi-listen-parity-pack@based-hardware-dev.iam.gserviceaccount.com
  KSA WI: based-hardware-dev.svc.id.goog[dev-omi-backend/dev-omi-backend-listen]

Also grants objectAdmin to the existing runtime JSON SA used by dev listen
(nik-164@based-hardware) so export works while GOOGLE_APPLICATION_CREDENTIALS /
SERVICE_ACCOUNT_JSON still point at that identity.
"""

from __future__ import annotations

import subprocess

PROJECT = "based-hardware-dev"
BUCKET = "based-hardware-dev-omi-parity-pack-v0"
# GCP service-account IDs must be 6–30 characters.
GSA_ID = "dev-omi-listen-parity-pack"
GSA_EMAIL = f"{GSA_ID}@{PROJECT}.iam.gserviceaccount.com"
KSA = "dev-omi-backend-listen"
NAMESPACE = "dev-omi-backend"
LOCATION = "us-central1"
# Current dev listen runtime credential (SERVICE_ACCOUNT_JSON).
RUNTIME_JSON_SA = "nik-164@based-hardware.iam.gserviceaccount.com"
PREFIX = "parity-pack/v0"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def ensure_gsa() -> None:
    describe = run(
        ["gcloud", "iam", "service-accounts", "describe", GSA_EMAIL, f"--project={PROJECT}"],
        check=False,
    )
    if describe.returncode == 0:
        print(f"GSA exists: {GSA_EMAIL}")
        return
    run(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "create",
            GSA_ID,
            f"--project={PROJECT}",
            "--display-name=Dev listen parity-pack export",
            "--description=Dev-only GSA for parity-pack cassette export (SCA-237)",
        ]
    )
    print(f"Created GSA: {GSA_EMAIL}")


def ensure_bucket() -> None:
    describe = run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{BUCKET}", f"--project={PROJECT}"],
        check=False,
    )
    if describe.returncode != 0:
        run(
            [
                "gcloud",
                "storage",
                "buckets",
                "create",
                f"gs://{BUCKET}",
                f"--project={PROJECT}",
                f"--location={LOCATION}",
                "--uniform-bucket-level-access",
                "--public-access-prevention",
            ]
        )
        print(f"Created bucket gs://{BUCKET}")
    else:
        print(f"Bucket exists: gs://{BUCKET}")
    run(
        [
            "gcloud",
            "storage",
            "buckets",
            "update",
            f"gs://{BUCKET}",
            "--public-access-prevention",
        ],
        check=False,
    )
    run(
        [
            "gcloud",
            "storage",
            "buckets",
            "update",
            f"gs://{BUCKET}",
            "--uniform-bucket-level-access",
        ],
        check=False,
    )


def ensure_bucket_iam(member_email: str) -> None:
    run(
        [
            "gcloud",
            "storage",
            "buckets",
            "add-iam-policy-binding",
            f"gs://{BUCKET}",
            f"--member=serviceAccount:{member_email}",
            "--role=roles/storage.objectAdmin",
            f"--project={PROJECT}",
        ]
    )
    print(f"Bound roles/storage.objectAdmin -> {member_email}")


def ensure_workload_identity() -> None:
    member = f"serviceAccount:{PROJECT}.svc.id.goog[{NAMESPACE}/{KSA}]"
    run(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "add-iam-policy-binding",
            GSA_EMAIL,
            f"--project={PROJECT}",
            f"--member={member}",
            "--role=roles/iam.workloadIdentityUser",
        ]
    )
    print(f"Bound workloadIdentityUser: {member} -> {GSA_EMAIL}")


def assert_not_public() -> None:
    result = run(
        [
            "gcloud",
            "storage",
            "buckets",
            "get-iam-policy",
            f"gs://{BUCKET}",
            f"--project={PROJECT}",
            "--format=json",
        ]
    )
    if "allUsers" in result.stdout or "allAuthenticatedUsers" in result.stdout:
        raise SystemExit(f"Refusing public IAM on gs://{BUCKET}")


def main() -> int:
    ensure_gsa()
    ensure_bucket()
    ensure_bucket_iam(GSA_EMAIL)
    ensure_bucket_iam(RUNTIME_JSON_SA)
    ensure_workload_identity()
    assert_not_public()
    print(f"Ensured private dev parity-pack bucket gs://{BUCKET}/{PREFIX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
