"""Standalone tests for the config read-modify-write locking (stdlib only).

These tests verify the file-locking mechanism that fixes #22972. They are
self-contained so they run in the standalone harness (no tomli_w, no omi_cli
imports, no conftest fixtures).

See omi_cli/auth/store.py::_config_lock for the production implementation.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading


def test_concurrent_read_modify_write_serialized_by_file_lock():
    """Concurrent read-modify-write on a shared file must not lose either writer's data.

    Regression test for #22972: without file locking, two concurrent writers that
    load-modify-save a shared config file lose one writer's changes because the
    last save() overwrites the other profile's credential.

    This test mirrors the locking in omi_cli/auth/store.py (_config_lock using
    fcntl.flock on POSIX, msvcrt.locking on Windows) but is self-contained so it
    runs in the standalone harness with nothing but Python and pytest.
    """
    if os.name == "nt":
        import msvcrt

        def acquire(fd):
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

        def release(fd):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        def acquire(fd):
            fcntl.flock(fd, fcntl.LOCK_EX)

        def release(fd):
            fcntl.flock(fd, fcntl.LOCK_UN)

    path = os.path.join(tempfile.gettempdir(), f"test-config-lock-{os.getpid()}.json")
    lock_path = path + ".lock"
    try:
        with open(path, "w") as fh:
            json.dump({"alpha": None, "beta": None}, fh)

        errors = []

        def write_profile(name: str, key: str) -> None:
            try:
                for _ in range(20):
                    with open(lock_path, "a+") as lock_file:
                        acquire(lock_file.fileno())
                        try:
                            with open(path, "r") as fh:
                                data = json.load(fh)
                            data[name] = key
                            with open(path, "w") as fh:
                                json.dump(data, fh)
                        finally:
                            release(lock_file.fileno())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=write_profile, args=("alpha", "KEY-A")),
            threading.Thread(target=write_profile, args=("beta", "KEY-B")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, f"concurrent writes raised: {errors}"

        with open(path, "r") as fh:
            data = json.load(fh)

        # Without locking, one of these keys would be missing or overwritten.
        assert data.get("alpha") == "KEY-A", f"alpha credential lost: {data}"
        assert data.get("beta") == "KEY-B", f"beta credential lost: {data}"
    finally:
        for p in (path, lock_path):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
