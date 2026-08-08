"""Finding #4: the outbound IdP credential exchange must not run on the shared ``critical_executor``.

``_generate_custom_token`` performs a ``signInWithIdp`` REST round-trip to the identity provider — an
outbound network hop with unpredictable latency. Running it on ``critical_executor`` (8 workers, shared
with token verification and rate-limit gates) lets a slow IdP starve every unrelated request. The fix
offloads the exchange to the dedicated ``auth_idp_executor`` bulkhead (mirroring ``stripe_executor``),
leaving fast local work (``mint_custom_token`` signs locally) on ``critical_executor``.

Hermetic: patches ``run_blocking`` to record which executor each offload targets and stubs the auth
adapter, so no real executor thread or network call runs.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Tuple

from routers import auth as auth_router
from utils import executors


class _FakeAdapter:
    def exchange_idp_credential(self, provider: str, id_token: str, access_token: Any = None) -> str:
        return "uid-xyz"

    def mint_custom_token(self, uid: str) -> str:
        return "custom-token"


def test_idp_exchange_offloaded_to_dedicated_executor(monkeypatch):
    calls: List[Tuple[Any, str]] = []

    async def tracking_run_blocking(executor: Any, func: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append((executor, getattr(func, "__name__", "")))
        return func(*args, **kwargs)

    monkeypatch.setattr(auth_router, "run_blocking", tracking_run_blocking)
    monkeypatch.setattr(auth_router, "get_auth_provider", lambda: _FakeAdapter())

    result = asyncio.run(auth_router._generate_custom_token("google", "id-token"))
    assert result == "custom-token"

    exchange_executors = [ex for ex, name in calls if name == "exchange_idp_credential"]
    # The outbound exchange runs on the dedicated external-I/O bulkhead...
    assert exchange_executors == [executors.auth_idp_executor]
    # ...and never on the shared critical gate.
    assert executors.critical_executor not in exchange_executors

    # Local key-signing stays on critical_executor (fast, no network) — unchanged.
    mint_executors = [ex for ex, name in calls if name == "mint_custom_token"]
    assert mint_executors == [executors.critical_executor]
