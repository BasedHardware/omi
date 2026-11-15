"""Local consent and private-file boundaries. No credentials or cloud imports."""

import hashlib
import os
from pathlib import Path
import re
import stat


class CaptureRefused(PermissionError):
    """Messages are fixed policy labels, never paths or input values."""


def private_text(path: Path) -> str:
    """Open without following symlinks; check the opened inode, not a prior stat."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
                raise CaptureRefused('private input requires an owned regular 0600 file')
            return stream.read()
    except (OSError, UnicodeError):
        raise CaptureRefused('private input unavailable') from None


def document_id(value: str) -> str:
    if not value or value in {'.', '..'} or '/' in value or any(ord(c) < 32 for c in value):
        raise CaptureRefused('invalid document identity')
    return value


def consenting_uid(uid_file: Path, consent_file: Path) -> str:
    """Pins are supplied by the consenting operator, never generated or extended here."""
    uid = document_id(private_text(uid_file).strip())
    pins = private_text(consent_file).splitlines()
    if not pins or any(not re.fullmatch(r'[0-9a-f]{64}', pin) for pin in pins):
        raise CaptureRefused('consent requires one sha256 per line')
    if hashlib.sha256(uid.encode()).hexdigest() not in pins:
        raise CaptureRefused('owner is not pinned for capture')
    return uid


def conversations(path: Path) -> list[str]:
    values = [document_id(line) for line in private_text(path).splitlines()]
    if not values or len(values) > 100 or len(set(values)) != len(values):
        raise CaptureRefused('select between one and 100 distinct conversations')
    return values


def private_directory(path: Path, *, create: bool = False) -> None:
    """Output must stay outside Git. Existing directories must already be private."""
    if any(parent.name == '.git' or (parent / '.git').exists() for parent in (path, *path.parents)):
        raise CaptureRefused('capture output must be outside Git')
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise CaptureRefused('capture output cannot follow symlinks')
    if create:
        path.mkdir(mode=0o700, exist_ok=False)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise CaptureRefused('capture output requires an owned 0700 directory')


def private_write(path: Path, body: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(body)


def without_uid(value, uid: str, token: str):
    """Remove UID even in nested values, map keys, references and object names.

    Replay must restore the operator's UID in memory before AEAD verification;
    ciphertext and its AAD are never rewritten by capture.
    """
    if isinstance(value, str):
        return value.replace(uid, token)
    if isinstance(value, list):
        return [without_uid(item, uid, token) for item in value]
    if isinstance(value, dict):
        return {without_uid(key, uid, token): without_uid(item, uid, token) for key, item in value.items()}
    return value
