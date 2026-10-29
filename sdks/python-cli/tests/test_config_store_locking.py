import pytest
from pathlib import Path
from omi_cli.auth.store import store_api_key
import threading
import tomli

def test_concurrent_store_api_key_different_profiles_both_survive(config_path: Path):
    """Verify that concurrent calls to store_api_key do not lose data.

    This test exercises the real locking mechanism by performing concurrent
    credential writes to the config file (isolated via the OMI_CONFIG
    environment variable provided by the test runner).
    """
    errors = []

    def worker(profile: str, key_prefix: str) -> None:
        try:
            for i in range(10):
                store_api_key(profile, f"{key_prefix}-{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("alpha", "KEY-A")),
        threading.Thread(target=worker, args=("beta", "KEY-B")),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"Concurrent store_api_key raised: {errors}"

    data = tomli.loads(config_path.read_text(encoding="utf-8"))
    
    assert "profiles" in data
    assert "alpha" in data["profiles"]
    assert "beta" in data["profiles"]
    assert data["profiles"]["alpha"]["api_key"] == "KEY-A-9"
    assert data["profiles"]["beta"]["api_key"] == "KEY-B-9"