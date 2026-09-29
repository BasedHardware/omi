"""DELETE must not be replayed when the server may already have applied it.

``_may_retry`` guards POST/PATCH against ambiguous replay but historically
omitted DELETE. A DELETE that fails with a lost response (ReadTimeout) or a
5xx is exactly as ambiguous as a POST: the server may have already removed the
resource. Replaying it is unsafe, and the retry also hides the ambiguity from
the caller instead of surfacing ``outcome unknown``.
"""

import time

import httpx
import pytest

from omi_cli.client import OmiClient
from omi_cli.errors import ServerError

PATH = "/v1/dev/user/conversations/c1"


@pytest.mark.parametrize("failure", ["timeout", "server_error"])
def test_ambiguous_delete_is_not_replayed(authed_profile, respx_mock, monkeypatch, failure):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    applied = []

    def server(request):
        applied.append(request.method)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic lost response", request=request)
        return httpx.Response(500, json={"detail": "response failed after commit"})

    respx_mock.route(method="DELETE", path=PATH).mock(side_effect=server)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError, match="outcome unknown") as info:
            client.delete(PATH)
    if failure == "server_error":
        assert "500" in info.value.message
        assert "check the resource" in info.value.detail
    assert len(applied) == 1


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_delete_retries_before_submission(authed_profile, respx_mock, monkeypatch, failure):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.delete(PATH).mock(side_effect=[failure("not submitted"), httpx.Response(204)])
    with OmiClient(authed_profile) as client:
        assert client.delete(PATH) is None
    assert route.call_count == 2
