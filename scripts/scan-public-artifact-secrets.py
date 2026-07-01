#!/usr/bin/env python3
"""Scan public release artifacts for server-only secret material."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "app" / "config" / "client_env_policy.yaml"
FORBIDDEN_FILENAMES = {
    ".dev.env",
    ".client.env",
    "google-credentials.json",
    "service-account.json",
}
FORBIDDEN_SUFFIXES = {".pem", ".p12", ".keystore"}


def load_policy() -> dict:
    with POLICY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def denied_patterns(policy: dict) -> list[re.Pattern[str]]:
    return [re.compile(pattern) for pattern in policy["server_secret_env"]["denied_name_patterns"]]


def name_is_denied(name: str, exact: set[str], patterns: list[re.Pattern[str]]) -> bool:
    return name in exact or any(pattern.search(name) for pattern in patterns)


def extract_zip(path: Path, dest: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        archive.extractall(dest)


def materialize(path: Path, dest: Path) -> Path:
    target = dest / path.name
    if path.is_dir():
        shutil.copytree(path, target)
        return target
    if zipfile.is_zipfile(path):
        target.mkdir(parents=True, exist_ok=True)
        extract_zip(path, target)
        return target
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target / path.name)
    return target


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def scan_artifact(path: Path, policy: dict) -> list[str]:
    errors: list[str] = []
    denied = set(policy["server_secret_env"]["denied_exact"])
    patterns = denied_patterns(policy)
    secret_values = {name: os.environ.get(name, "").encode() for name in denied if os.environ.get(name)}

    with tempfile.TemporaryDirectory(prefix="omi-public-artifact-scan-") as raw_tmp:
        extracted_root = materialize(path, Path(raw_tmp))
        nested_archives = [p for p in iter_files(extracted_root) if p.suffix.lower() in {".zip", ".apk", ".aab"}]
        for archive_path in nested_archives:
            if zipfile.is_zipfile(archive_path):
                nested_dest = archive_path.with_suffix(archive_path.suffix + ".extracted")
                nested_dest.mkdir(exist_ok=True)
                extract_zip(archive_path, nested_dest)

        for file_path in iter_files(extracted_root):
            lower_name = file_path.name.lower()
            rel = file_path.relative_to(extracted_root)
            if lower_name in FORBIDDEN_FILENAMES or file_path.suffix.lower() in FORBIDDEN_SUFFIXES:
                errors.append(f"{path}: forbidden file bundled in public artifact: {rel}")
                continue

            data = read_bytes(file_path)
            if not data:
                continue
            if file_path.name.endswith(".env") or file_path.name == ".env":
                for lineno, raw_line in enumerate(data.decode("utf-8", errors="ignore").splitlines(), start=1):
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name = line.split("=", 1)[0].strip()
                    if name_is_denied(name, denied, patterns):
                        errors.append(f"{path}: server-only variable name {name} appears in {rel}:{lineno}")
            for name in denied:
                if name.encode() in data:
                    errors.append(f"{path}: server-only variable name {name} appears in {rel}")
            for name, value in secret_values.items():
                if value and value in data:
                    errors.append(f"{path}: current CI value for {name} appears in {rel}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="*", type=Path, help="IPA/AAB/APK/app/zip/directory artifacts to scan")
    args = parser.parse_args()

    policy = load_policy()
    errors: list[str] = []
    for artifact in args.artifacts:
        if not artifact.exists():
            errors.append(f"{artifact}: artifact does not exist")
            continue
        errors.extend(scan_artifact(artifact, policy))

    if errors:
        print("Public artifact secret scan failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Public artifact secret scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
