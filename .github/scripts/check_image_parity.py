#!/usr/bin/env python3
"""Q6 (ADR-0050): keep the shared container images pinned identically in the compose stack and the Helm
chart, so the two on-prem deployment targets never drift.

The image pins live in two places by design (compose files + Helm values). Rather than a shared
manifest file (which would need both consumers to read a third format), this check is the source of
truth for parity: it extracts the pin of every SHARED component from both and fails on any mismatch.

Components that exist in only one target (the built ``omi-onprem-backend`` image; the CI's minio/mc
bucket-init helper) are not shared and are ignored. Stdlib only (regex), like the other guards.

Run:  python3 .github/scripts/check_image_parity.py   # exit 0 = in sync
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = [ROOT / "deploy/onprem/compose.base.yaml", ROOT / "deploy/onprem/compose.selfhost.yaml"]
VALUES = ROOT / "deploy/onprem/helm/omi-onprem/values.yaml"

# Shared components: a stable substring that identifies the image in BOTH files.
SHARED = {
    "mongo": "mongo:",
    "valkey": "valkey/valkey:",
    "qdrant": "qdrant/qdrant",
    "rustfs": "rustfs/rustfs:",
    "ntfy": "binwiederhier/ntfy:",
    "keycloak": "quay.io/keycloak/keycloak:",
}

_IMAGE_RE = re.compile(r'image:\s*["\']?([^\s"\']+)')


def _images(text: str) -> list[str]:
    return _IMAGE_RE.findall(text)


def _find(images: list[str], marker: str) -> str | None:
    hits = sorted({img for img in images if marker in img})
    if len(hits) > 1:
        raise SystemExit(f"ambiguous image for marker {marker!r}: {hits}")
    return hits[0] if hits else None


def main() -> int:
    compose_imgs: list[str] = []
    for f in COMPOSE:
        compose_imgs += _images(f.read_text(encoding="utf-8"))
    helm_imgs = _images(VALUES.read_text(encoding="utf-8"))

    problems = []
    for name, marker in SHARED.items():
        c = _find(compose_imgs, marker)
        h = _find(helm_imgs, marker)
        if c is None or h is None:
            problems.append(f"{name}: missing pin (compose={c!r}, helm={h!r})")
        elif c != h:
            problems.append(f"{name}: DRIFT\n    compose: {c}\n    helm:    {h}")

    if problems:
        print("Image parity check FAILED (compose <-> Helm):\n  " + "\n  ".join(problems))
        print("\nFix: pin the same ref in deploy/onprem/compose.*.yaml and deploy/onprem/helm/omi-onprem/values.yaml")
        return 1
    print(f"Image parity OK — {len(SHARED)} shared components pinned identically in compose and Helm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
