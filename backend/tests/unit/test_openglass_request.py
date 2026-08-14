from types import SimpleNamespace

import pytest

from utils.llm import openglass


@pytest.mark.asyncio
async def test_describe_image_passes_luna_completion_budget_as_request_kwarg(monkeypatch):
    request: dict[str, object] = {}

    class FakeLlm:
        async def ainvoke(self, input, **kwargs):
            request["input"] = input
            request.update(kwargs)
            return SimpleNamespace(content="A desk with a laptop.")

    monkeypatch.setattr(openglass, "get_llm", lambda _feature: FakeLlm())

    description = await openglass.describe_image("user-1", "aW1hZ2U=")

    assert description == "A desk with a laptop."
    assert request["max_completion_tokens"] == 150
    assert "config" not in request
