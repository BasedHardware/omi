"""Smoke: packages.platform re-exports stay importable."""


def test_packages_platform_sanitize_roundtrip():
    from packages.platform import sanitize

    assert sanitize("hello") == "hello"


def test_packages_platform_encryption_symbols():
    from packages import platform as plat

    assert callable(plat.encrypt)
    assert callable(plat.decrypt)
    assert callable(plat.derive_key)
    assert callable(plat.sanitize_pii)
