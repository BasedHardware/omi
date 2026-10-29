"""Test Windows configuration locks without touching a real Omi config."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from omi_cli import config as cfg


class _FakeWinFunction:
    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: object) -> int:
        self.calls.append(args)
        return self.result


def test_windows_lock_uses_blocking_exclusive_byte_zero_and_matching_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise API flags and the lock range even on non-Windows test hosts."""
    lock, unlock = _FakeWinFunction(1), _FakeWinFunction(1)
    kernel = SimpleNamespace(LockFileEx=lock, UnlockFileEx=unlock)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda fd: fd + 100))
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: kernel, raising=False)

    cfg._windows_config_lock(7, unlock=False)
    cfg._windows_config_lock(7, unlock=True)

    assert lock.calls[0][:5] == (107, 2, 0, 1, 0)  # exclusive, no fail-immediately, one byte
    assert unlock.calls[0][:4] == (107, 0, 1, 0)
    for args in (lock.calls[0], unlock.calls[0]):
        overlapped = args[-1]._obj  # type: ignore[attr-defined]
        assert overlapped.Offset == overlapped.OffsetHigh == 0
        assert not overlapped.hEvent


@pytest.mark.parametrize("unlock", [False, True], ids=["acquire", "release"])
def test_windows_lock_api_failure_is_propagated(monkeypatch: pytest.MonkeyPatch, unlock: bool) -> None:
    kernel = SimpleNamespace(LockFileEx=_FakeWinFunction(0), UnlockFileEx=_FakeWinFunction(0))
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda fd: fd))
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: kernel, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(ctypes, "WinError", lambda code: OSError(code, "synthetic native failure"), raising=False)

    with pytest.raises(OSError, match="synthetic native failure"):
        cfg._windows_config_lock(7, unlock=unlock)


def test_lock_acquisition_failure_does_not_read_or_write_config(
    monkeypatch: pytest.MonkeyPatch, config_path: Path
) -> None:
    """A failed lock must not fall through to an unprotected transaction."""
    original = b"[profiles.default]\napi_base = 'https://example.invalid'\n"
    config_path.write_bytes(original)

    def fail(_fd: int) -> None:
        raise PermissionError("synthetic lock failure")

    monkeypatch.setattr(cfg, "_acquire_config_lock", fail)
    with pytest.raises(PermissionError, match="synthetic lock failure"):
        with cfg.locked_config(config_path):
            pytest.fail("an unprotected transaction was entered")
    assert config_path.read_bytes() == original


# The native tests below run only on real Windows. Child processes receive a
# temporary HOME and explicit temporary OMI_CONFIG; they make no network calls.
_NATIVE_WAITER = r"""
import os, sys
from pathlib import Path
from omi_cli import config as cfg
lock_path, started, acquired = map(Path, sys.argv[1:])
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
try:
    started.write_text('started')
    cfg._acquire_config_lock(fd)
    try:
        acquired.write_text('acquired')
    finally:
        cfg._release_config_lock(fd)
finally:
    os.close(fd)
"""

_NATIVE_HOLDER = r"""
import os, sys
from pathlib import Path
from omi_cli import config as cfg
lock_path, acquired = map(Path, sys.argv[1:])
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
try:
    cfg._acquire_config_lock(fd)
    acquired.write_text('acquired')
    sys.stdin.read()
finally:
    os.close(fd)
"""

_LEGACY_PROBE = r"""
import errno, msvcrt, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
try:
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        # Only the expected CRT lock-contention errors are evidence of mutual
        # exclusion; bad descriptors and unrelated failures must surface.
        if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
            raise
        sys.exit(42)
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
finally:
    os.close(fd)
"""


def _child_env(tmp_path: Path) -> dict[str, str]:
    source = Path(cfg.__file__).resolve().parent.parent
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR") if k in os.environ}
    env.update(
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),
        OMI_CONFIG=str(tmp_path / "config.toml"),
        PYTHONPATH=str(source),
    )
    return env


def _wait_for_file(path: Path, child: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    while not path.exists():
        if child.poll() is not None:
            stdout, stderr = child.communicate(timeout=2)
            pytest.fail(f"child exited before {path.name}: {child.returncode}; {stdout}; {stderr}")
        if time.monotonic() >= deadline:
            pytest.fail(f"child did not produce {path.name}")
        time.sleep(0.01)


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows byte-range locks")
def test_windows_waits_beyond_crt_timeout_and_interoperates_with_legacy_lock(tmp_path: Path) -> None:
    import msvcrt

    lock_path = tmp_path / "config.toml.lock"
    started, acquired = tmp_path / "started", tmp_path / "acquired"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
    child: subprocess.Popen[str] | None = None
    locked = False
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        locked = True
        child = subprocess.Popen(
            [sys.executable, "-c", _NATIVE_WAITER, str(lock_path), str(started), str(acquired)],
            env=_child_env(tmp_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _wait_for_file(started, child)
        # The CRT's LK_LOCK gives up after about 10 one-second retries. Our
        # waiter must still be waiting while an older client holds that byte.
        with pytest.raises(subprocess.TimeoutExpired):
            child.wait(timeout=11)
        assert not acquired.exists()
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        locked = False
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, f"waiter failed: {stdout}; {stderr}"
        assert acquired.exists()
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
        if locked:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows byte-range locks")
def test_windows_legacy_client_observes_lock_and_process_exit_releases_it(tmp_path: Path) -> None:
    lock_path, acquired = tmp_path / "config.toml.lock", tmp_path / "acquired"
    child = subprocess.Popen(
        [sys.executable, "-c", _NATIVE_HOLDER, str(lock_path), str(acquired)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_child_env(tmp_path),
    )
    try:
        _wait_for_file(acquired, child)
        blocked = subprocess.run(
            [sys.executable, "-c", _LEGACY_PROBE, str(lock_path)],
            env=_child_env(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert blocked.returncode == 42, f"legacy lock was not blocked: {blocked.stdout}; {blocked.stderr}"
        child.kill()
        child.communicate(timeout=10)
        released = subprocess.run(
            [sys.executable, "-c", _LEGACY_PROBE, str(lock_path)],
            env=_child_env(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert released.returncode == 0, f"lock was not released: {released.stdout}; {released.stderr}"
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
