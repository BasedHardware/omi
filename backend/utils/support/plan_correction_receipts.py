"""Keep owner lists and plan correction receipts inside the private triage checkout."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, TextIO
from urllib.parse import urlsplit

OWNER = re.compile(r'[A-Za-z0-9_-]{1,128}')


class PrivatePacketError(ValueError):
    pass


class PrivatePacket:
    def __init__(self, root: Path, expected_origin: str):
        url = urlsplit(expected_origin)
        if (
            url.scheme != 'ssh'
            or url.username != 'git'
            or not url.hostname
            or not url.path
            or url.password is not None
            or url.query
            or url.fragment
        ):
            raise PrivatePacketError('expected the private Forgejo SSH origin')
        self.root = root.resolve(strict=True)
        if self.root.stat().st_mode & 0o077:
            raise PrivatePacketError('private checkout must be accessible only to the operator')
        if self._git('rev-parse', '--show-toplevel').strip() != str(self.root):
            raise PrivatePacketError('expected the root of the private checkout')
        for direction in ((), ('--push',)):
            if self._git('remote', 'get-url', '--all', *direction, 'origin').splitlines() != [expected_origin]:
                raise PrivatePacketError('private checkout origin does not match')

    def _git(self, *args: str) -> str:
        return subprocess.check_output(
            ['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL, text=True, timeout=10
        )

    @staticmethod
    def _packet_path(value: str) -> Path:
        path = Path(value)
        if not path.parts or path.parts[0] != 'packets' or len(path.parts) < 2 or '..' in path.parts:
            raise PrivatePacketError('expected a path under packets/')
        return path

    def _committed(self, value: str) -> str:
        path = self._packet_path(value)
        return self._git('show', f'refs/remotes/origin/main:{path.as_posix()}')

    def owners(self, value: str) -> list[str]:
        return self._committed(value).splitlines()

    def receipt(self, value: str) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self._committed(value).splitlines()]

    def new_receipt(self, value: str) -> TextIO:
        path = self.root / self._packet_path(value)
        if path.parent.resolve(strict=True) != path.parent:
            raise PrivatePacketError('receipt directory must be inside the private checkout without symlinks')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        return os.fdopen(fd, 'w', encoding='utf-8')


def append_receipt(handle: TextIO, entry: dict[str, Any]) -> None:
    handle.write(json.dumps(entry, sort_keys=True) + '\n')
    handle.flush()
    os.fsync(handle.fileno())
