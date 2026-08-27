#!/usr/bin/env python3
"""ADR-0055: keep every third-party image pin in ONE place and make the two deployment targets derive
from it.

``deploy/onprem/omi.oss.release.pins`` is the source of truth. Compose reads it natively (the long form
of ``include:`` passes it as an ``env_file``, so every ``image:`` in the included files is an
``${OMI_OSS_*_IMAGE}`` reference). Helm cannot read a file outside the chart directory, so the chart is a
PROJECTION: ``values.yaml`` repeats the pins in its own format and this check keeps it honest.

Supersedes the ADR-0050 model (two native formats + drift detection). Consequences of the change:
compose drift is now impossible by construction rather than detected, and the coverage extends to the
components that live in only ONE target (nginx in compose, postgres/mc in Helm) — those were outside the
old check by design.

Each pin holds the WHOLE image reference, so tag / tag@digest / bare digest are all fine: this check
compares strings and never parses a version.

Run:  python3 .github/scripts/check_oss_image_parity.py   # exit 0 = in sync
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "deploy/onprem/omi.oss.release.pins"
COMPOSE = [ROOT / "deploy/onprem/compose.base.yaml", ROOT / "deploy/onprem/compose.selfhost.yaml"]
VALUES = ROOT / "deploy/onprem/helm/omi-oss/values.yaml"

# component -> (pins variable, substring identifying the image in values.yaml or None if Helm has no
# equivalent). A component present in only one target is still pinned centrally (ADR-0055).
COMPONENTS = {
    "valkey": ("OMI_OSS_VALKEY_IMAGE", "valkey/valkey:"),
    "mongo": ("OMI_OSS_MONGO_IMAGE", "mongo:"),
    "keycloak": ("OMI_OSS_KEYCLOAK_IMAGE", "quay.io/keycloak/keycloak:"),
    "ntfy": ("OMI_OSS_NTFY_IMAGE", "binwiederhier/ntfy:"),
    "qdrant": ("OMI_OSS_QDRANT_IMAGE", "qdrant/qdrant"),
    "rustfs": ("OMI_OSS_RUSTFS_IMAGE", "rustfs/rustfs:"),
    "typesense": ("OMI_OSS_TYPESENSE_IMAGE", "typesense/typesense:"),
    "postgres": ("OMI_OSS_POSTGRES_IMAGE", "postgres:"),
    "mc": ("OMI_OSS_MC_IMAGE", "minio/mc:"),
    # TLS-terminating reverse proxies: compose only (Helm terminates at the Envoy Gateway).
    "nginx": ("OMI_OSS_NGINX_IMAGE", None),
    # The Python base our backend image is BUILT from: a compose build-arg, not a service `image:`,
    # and absent from Helm (the chart consumes the built image). Pinned here anyway, because a
    # floating base tag is exactly the drift ADR-0055 exists to stop — it moved from 3.11.15 to
    # 3.11.16 under us and made upstream's unit runner refuse to start.
    "python-base": ("OMI_OSS_PYTHON_BASE_IMAGE", None),
}

# Whole value, not the first token: a `${VAR:?message}` reference contains spaces. Also matches the
# camelCase keys the chart uses for helper images (`mcImage:`).
_IMAGE_RE = re.compile(r'^\s*\w*[iI]mage:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
# `${OMI_OSS_X_IMAGE:?msg}` — the message may contain anything but `}`.
_PIN_REF_RE = re.compile(r"^\$\{(OMI_OSS_[A-Z0-9_]+_IMAGE)(:[?-][^}]*)?\}$")
# Images we build ourselves carry the release, not a pin (ADR-0054) — out of scope here.
_OURS_RE = re.compile(r"^\$?\{?omi-oss-|^\$\{OMI_OSS_RELEASE")
# Any pin reference, wherever it appears. A pin can be consumed by something that is not a service
# `image:` — `PYTHON_BASE_IMAGE:` under `build.args` is one — and rule 4 must count that as usage or
# it reports a live pin as dead.
_ANY_PIN_REF_RE = re.compile(r"\$\{(OMI_OSS_[A-Z0-9_]+_IMAGE)(?::[?-][^}]*)?\}")


def _parse_pins(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        pins[key.strip()] = value.strip()
    return pins


def _images(text: str) -> list[str]:
    """Image values, one per `image:`/`*Image:` line, with any trailing YAML comment removed.

    A comment is only stripped OUTSIDE a `${...}` reference, so the human-readable message of a
    `${VAR:?why}` survives intact.
    """
    out = []
    for raw in _IMAGE_RE.findall(text):
        value = raw if raw.startswith("${") else raw.split("#", 1)[0].strip()
        if value:
            out.append(value)
    return out


def _find(images: list[str], marker: str) -> str | None:
    hits = sorted({img for img in images if marker in img})
    if len(hits) > 1:
        raise SystemExit(f"ambiguous image for marker {marker!r}: {hits}")
    return hits[0] if hits else None


def check(pins_text: str, compose_texts: dict[str, str], values_text: str) -> list[str]:
    """The whole rule, over source strings — so it is testable without a repo on disk."""
    problems: list[str] = []
    pins = _parse_pins(pins_text)

    # 1. Every pin the components need exists in the file.
    for name, (var, _) in COMPONENTS.items():
        if var not in pins:
            problems.append(f"{name}: {var} missing from {PINS.name}")

    # 2. No compose file pins a third-party image inline: it must reference a pin (or be one of OUR
    #    images, which carry the release instead). This is what makes compose drift impossible.
    used: set[str] = set()
    for fname, text in compose_texts.items():
        used.update(_ANY_PIN_REF_RE.findall(text))
        for img in _images(text):
            ref = _PIN_REF_RE.match(img)
            if ref:
                used.add(ref.group(1))
                if ref.group(1) not in pins:
                    problems.append(f"{fname}: references {ref.group(1)}, absent from {PINS.name}")
            elif not _OURS_RE.match(img):
                problems.append(
                    f"{fname}: inline third-party pin {img!r} — move it to {PINS.name} and reference "
                    f"it as ${{OMI_OSS_<NAME>_IMAGE:?...}}"
                )

    # 3. The Helm projection agrees with the pins, component by component.
    helm_imgs = _images(values_text)
    for name, (var, marker) in COMPONENTS.items():
        if marker is None:
            continue
        want, got = pins.get(var), _find(helm_imgs, marker)
        if got is None:
            problems.append(f"{name}: missing pin in Helm values (expected {want!r})")
        elif want != got:
            problems.append(f"{name}: DRIFT\n    pins: {want}\n    helm: {got}")

    # 4. A pin nobody uses is either dead or a typo in a reference.
    for var in sorted(set(pins) - {v for v, _ in COMPONENTS.values()}):
        problems.append(f"{var}: pinned in {PINS.name} but unknown to this check (add it to COMPONENTS)")
    for name, (var, marker) in COMPONENTS.items():
        if marker is None and var not in used:
            problems.append(f"{name}: {var} is compose-only but no compose file references it")

    return problems


def main() -> int:
    problems = check(
        PINS.read_text(encoding="utf-8"),
        {f.name: f.read_text(encoding="utf-8") for f in COMPOSE},
        VALUES.read_text(encoding="utf-8"),
    )
    if problems:
        print("Image pin check FAILED:\n  " + "\n  ".join(problems))
        print(f"\nFix: {PINS.name} is the source of truth; compose references it, Helm values mirror it.")
        return 1

    print(f"Image pins OK — {len(COMPONENTS)} third-party components pinned in {PINS.name}; "
          f"compose references them, Helm values match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
