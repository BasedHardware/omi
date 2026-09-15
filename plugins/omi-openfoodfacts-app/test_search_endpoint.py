"""Full-text search endpoint contract (#13190)."""

import asyncio


def test_search_foods_uses_cgi_fulltext_endpoint(monkeypatch):
    import main

    captured = {}

    async def fake_get_async(path, params=None):
        captured["path"] = path
        captured["params"] = params or {}
        return {"products": [{"code": "1", "product_name": "Oat milk"}], "count": 1}

    monkeypatch.setattr(main, "_openfoodfacts_get_async", fake_get_async)

    result = asyncio.get_event_loop().run_until_complete(main._search_foods("oat milk", 5))
    assert captured["path"] == "/cgi/search.pl"
    assert captured["params"]["search_terms"] == "oat milk"
    assert captured["params"]["json"] == 1
    assert result["count"] == 1
    assert result["products"][0]["name"] == "Oat milk"
