"""Unit tests for URL and port validation in ``omi_cli.webhook_target.inspect_target``."""

from __future__ import annotations

from omi_cli import webhook_target


def _unexpected_resolve(host: str) -> list[str]:
    raise AssertionError(f"Resolver should not be called for invalid URL (got {host!r})")


def test_inspect_target_rejects_malformed_ipv6_url_without_raising() -> None:
    report = webhook_target.inspect_target("https://[::1/hook", resolver=_unexpected_resolve)

    assert report.ok is False
    assert report.summary == "The URL is malformed"
    assert report.detail is not None


def test_inspect_target_rejects_non_numeric_and_out_of_range_ports() -> None:
    for url in (
        "https://example.com:abc/hook",
        "https://example.com:99999/hook",
        "https://example.com:0/hook",
    ):
        report = webhook_target.inspect_target(url, resolver=_unexpected_resolve)
        assert report.ok is False, url
        assert report.summary == "The URL has an invalid port", url
        assert report.detail is not None, url


def test_inspect_target_accepts_valid_explicit_port() -> None:
    report = webhook_target.inspect_target(
        "https://example.com:8443/hook",
        resolver=lambda _: ["93.184.216.34"],
    )

    assert report.ok is True
    assert report.summary == "example.com resolves to 93.184.216.34"
    assert report.detail is None
