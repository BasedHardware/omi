#!/usr/bin/env python3
"""Scan public release artifacts for server-only secret material."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "app" / "config" / "client_env_policy.yaml"
FORBIDDEN_FILENAMES = {
    ".dev.env",
    ".prod.env",
    ".client.env",
    ".client.dev.env",
    "google-credentials.json",
    "service-account.json",
}
FORBIDDEN_SUFFIXES = {".pem", ".p12", ".keystore", ".jks", ".p8"}
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b'"private_key"',
    b"'private_key'",
)
SECRET_VALUE_PATTERNS = (
    (re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b"), "OpenAI-shaped secret"),
    (re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{16,}\b"), "Anthropic-shaped secret"),
    (re.compile(rb"\bdg_[0-9A-Za-z]{20,}\b"), "Deepgram-shaped secret"),
    (re.compile(rb"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"), "Slack token-shaped secret"),
)
ALLOWED_PLACEHOLDER_TOKENS = {"YOUR_API_KEY"}
ZIP_SUFFIXES = {".zip", ".ipa", ".apk", ".aab", ".jar", ".aar"}
TAR_SUFFIXES = {".tar", ".tgz"}
FAIL_CLOSED_SUFFIXES = {".7z", ".rar", ".pkg", ".dmg"}
FRAMEWORK_DIR_SUFFIXES = (".framework", ".xcframework")
HEURISTIC_SCAN_EXTENSIONS = {
    ".bash",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".dart",
    ".env",
    ".go",
    ".graphql",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".log",
    ".m",
    ".mm",
    ".plist",
    ".properties",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def is_text_heuristic_file(file_path: Path, rel: Path) -> bool:
    """Return True for source/config text files that should get name heuristics."""
    if any(part.endswith(FRAMEWORK_DIR_SUFFIXES) for part in rel.parts):
        return False
    return file_path.suffix.lower() in HEURISTIC_SCAN_EXTENSIONS


def load_policy() -> dict:
    with POLICY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def denied_patterns(policy: dict) -> list[re.Pattern[str]]:
    return [re.compile(pattern) for pattern in policy["server_secret_env"]["denied_name_patterns"]]


def allowed_names(policy: dict) -> set[str]:
    return set(policy["public_client_env"]["allowed"]) | set(
        policy.get("legacy_public_client_env", {}).get("allowed", [])
    )


def allowed_public_token_names(policy: dict) -> set[str]:
    return allowed_names(policy) | set(policy.get("allowed_public_client_tokens", []))


def name_is_denied(name: str, exact: set[str], patterns: list[re.Pattern[str]]) -> bool:
    return name in exact or any(pattern.search(name) for pattern in patterns)


def is_public_firebase_config(rel: Path) -> bool:
    return rel.name in {"GoogleService-Info.plist", "google-services.json"}


def extract_zip(path: Path, dest: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        dest_root = dest.resolve()
        for member in archive.infolist():
            member_path = Path(member.filename)
            target = (dest / member.filename).resolve()
            if member_path.is_absolute() or ".." in member_path.parts or not target.is_relative_to(dest_root):
                raise ValueError(f"unsafe zip member path: {member.filename}")
        archive.extractall(dest)


def looks_like_tar(path: Path) -> bool:
    lower_path = str(path).lower()
    return path.suffix.lower() in TAR_SUFFIXES or lower_path.endswith((".tar.gz", ".tar.bz2", ".tar.xz"))


def extract_tar(path: Path, dest: Path) -> None:
    with tarfile.open(path) as archive:
        dest_root = dest.resolve()
        for member in archive.getmembers():
            member_path = Path(member.name)
            target = (dest / member.name).resolve()
            if member_path.is_absolute() or ".." in member_path.parts or not target.is_relative_to(dest_root):
                raise ValueError(f"unsafe tar member path: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"tar member links are not allowed: {member.name}")
        archive.extractall(dest)


def extract_dmg(path: Path, dest: Path, errors: list[str]) -> Path:
    target = dest / path.name
    target.mkdir(parents=True, exist_ok=True)
    if sys.platform != "darwin" or not shutil.which("hdiutil"):
        errors.append(f"{path}: cannot inspect DMG on this runner; scan must fail closed")
        return target

    mountpoint = dest / f"{path.stem}.mount"
    mountpoint.mkdir(parents=True, exist_ok=True)
    attached = False
    try:
        subprocess.run(
            [
                "hdiutil",
                "attach",
                "-readonly",
                "-nobrowse",
                "-mountpoint",
                str(mountpoint),
                str(path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        attached = True
        for child in mountpoint.iterdir():
            destination = target / child.name
            if child.is_dir():
                shutil.copytree(child, destination, symlinks=True)
            else:
                shutil.copy2(child, destination, follow_symlinks=False)
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f"{path}: failed to inspect DMG: {exc}")
    finally:
        if attached:
            subprocess.run(["hdiutil", "detach", str(mountpoint)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return target


def materialize(path: Path, dest: Path, errors: list[str]) -> Path:
    target = dest / path.name
    if path.is_dir():
        shutil.copytree(path, target)
        return target
    if path.suffix.lower() == ".dmg":
        return extract_dmg(path, dest, errors)
    suffix = path.suffix.lower()
    if suffix in FAIL_CLOSED_SUFFIXES:
        target.mkdir(parents=True, exist_ok=True)
        errors.append(f"{path}: cannot inspect {suffix} directly; scan the source bundle before packaging")
        return target
    if zipfile.is_zipfile(path) or suffix in ZIP_SUFFIXES:
        target.mkdir(parents=True, exist_ok=True)
        if zipfile.is_zipfile(path):
            try:
                extract_zip(path, target)
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                errors.append(f"{path}: failed to inspect zip archive: {exc}")
        else:
            errors.append(f"{path}: {suffix} is expected to be zip-compatible but could not be opened")
        return target
    if looks_like_tar(path):
        target.mkdir(parents=True, exist_ok=True)
        try:
            extract_tar(path, target)
        except (tarfile.TarError, ValueError) as exc:
            errors.append(f"{path}: failed to inspect tar archive: {exc}")
        return target
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target / path.name)
    return target


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def read_bytes(path: Path, errors: list[str], root_artifact: Path, rel: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        errors.append(f"{root_artifact}: failed to read bundled file {rel}: {exc}")
        return b""


def scan_artifact(path: Path, policy: dict) -> list[str]:
    errors: list[str] = []
    denied = set(policy["server_secret_env"]["denied_exact"])
    patterns = denied_patterns(policy)
    allowed = allowed_names(policy)
    allowed_public_tokens = allowed_public_token_names(policy)
    secret_values = {
        name: value.encode()
        for name, value in os.environ.items()
        if value
        and len(value) >= 8
        and not name.startswith(("PUBLIC_", "NEXT_PUBLIC_"))
        and name not in allowed_public_tokens
        and name_is_denied(name, denied, patterns)
    }

    with tempfile.TemporaryDirectory(prefix="omi-public-artifact-scan-") as raw_tmp:
        extracted_root = materialize(path, Path(raw_tmp), errors)
        processed_archives: set[Path] = set()
        while True:
            nested_archives = [
                p
                for p in iter_files(extracted_root)
                if p not in processed_archives
                and (p.suffix.lower() in ZIP_SUFFIXES or looks_like_tar(p) or p.suffix.lower() in FAIL_CLOSED_SUFFIXES)
            ]
            if not nested_archives:
                break
            for archive_path in nested_archives:
                processed_archives.add(archive_path)
                nested_dest = archive_path.with_suffix(archive_path.suffix + ".extracted")
                nested_dest.mkdir(exist_ok=True)
                rel_archive = archive_path.relative_to(extracted_root)
                if archive_path.suffix.lower() == ".dmg":
                    errors.append(f"{path}: nested DMG must not be bundled in public artifact: {rel_archive}")
                elif zipfile.is_zipfile(archive_path):
                    try:
                        extract_zip(archive_path, nested_dest)
                    except (OSError, ValueError, zipfile.BadZipFile) as exc:
                        errors.append(f"{path}: failed to inspect nested zip archive {rel_archive}: {exc}")
                elif looks_like_tar(archive_path):
                    try:
                        extract_tar(archive_path, nested_dest)
                    except (tarfile.TarError, ValueError) as exc:
                        errors.append(f"{path}: failed to inspect nested tar archive {rel_archive}: {exc}")
                else:
                    errors.append(f"{path}: unsupported nested archive {rel_archive}")

            # Continue until newly extracted archives have also been inspected.

        for file_path in iter_files(extracted_root):
            lower_name = file_path.name.lower()
            rel = file_path.relative_to(extracted_root)
            if lower_name in FORBIDDEN_FILENAMES or file_path.suffix.lower() in FORBIDDEN_SUFFIXES:
                errors.append(f"{path}: forbidden file bundled in public artifact: {rel}")
                continue

            data = read_bytes(file_path, errors, path, rel)
            if not data:
                continue
            text_heuristic_file = is_text_heuristic_file(file_path, rel)
            if text_heuristic_file:
                for marker in PRIVATE_KEY_MARKERS:
                    if marker in data:
                        errors.append(f"{path}: private key material appears in {rel}")
            for pattern, label in SECRET_VALUE_PATTERNS:
                if pattern.search(data):
                    errors.append(f"{path}: {label} appears in {rel}")
            if file_path.name.endswith(".env") or file_path.name == ".env":
                for lineno, raw_line in enumerate(data.decode("utf-8", errors="ignore").splitlines(), start=1):
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name = line.split("=", 1)[0].strip()
                    if name not in allowed_public_tokens:
                        errors.append(f"{path}: non-allowlisted variable name {name} appears in {rel}:{lineno}")
                    if name not in allowed_public_tokens and name_is_denied(name, denied, patterns):
                        errors.append(f"{path}: server-only variable name {name} appears in {rel}:{lineno}")
            if text_heuristic_file:
                for name in denied:
                    if name not in allowed_public_tokens and name.encode() in data:
                        errors.append(f"{path}: server-only variable name {name} appears in {rel}")
            if text_heuristic_file and not is_public_firebase_config(rel):
                text = data.decode("utf-8", errors="ignore")
                for token in set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text)):
                    if token in ALLOWED_PLACEHOLDER_TOKENS:
                        continue
                    if token not in allowed_public_tokens and name_is_denied(token, denied, patterns):
                        errors.append(f"{path}: server-only variable-like token {token} appears in {rel}")
            for name, value in secret_values.items():
                if value and value in data:
                    errors.append(f"{path}: current CI value for {name} appears in {rel}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="*", type=Path, help="IPA/AAB/APK/app/zip/directory artifacts to scan")
    args = parser.parse_args()

    if not args.artifacts:
        print("WARNING: No artifacts to scan (glob matched nothing). Skipping.", file=sys.stderr)
        return 0

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
