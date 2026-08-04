import asyncio

import pytest

from testing.replay_harness_llm_gateway_fake_upstream import oracle


def test_loopback_oracle_bypasses_ambient_proxy_configuration(monkeypatch) -> None:
    """A poisoned proxy must not intercept the local fake-upstream request."""

    for name in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    evidence = oracle.run_oracle()

    assert evidence["provider_request_count"] == 1
    assert evidence["status_classes"] == ["2xx", "4xx"]


def test_stalled_in_process_request_is_cancelled_by_the_deadline() -> None:
    """Exercise cancellation without using a wall-clock wait in the regression."""

    class StalledClient:
        def __init__(self) -> None:
            self.started = False
            self.cancelled = False

        async def post(self, *_args, **_kwargs) -> None:
            self.started = True
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    client = StalledClient()

    with pytest.raises(oracle.OracleFailure, match="bounded deadline"):
        asyncio.run(
            oracle._post_with_deadline(
                client,
                path=oracle.GATEWAY_PATH,
                payload=oracle._valid_gateway_request(),
                headers={},
                deadline_seconds=0,
            )
        )

    assert client.started
    assert client.cancelled
