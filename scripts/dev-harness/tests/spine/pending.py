"""Strict expected failure, never a skipped contract."""
import pytest


def pending(package: str):
    return pytest.mark.xfail(
        strict=True,
        raises=(AssertionError, NotImplementedError, pytest.fail.Exception),
        reason=f"PENDING CONTRACT {package}: remove marker when implemented",
    )
