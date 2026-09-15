"""Full-text search endpoint contract (#13190)."""

import asyncio


def test_search_foods_uses_cgi_fulltext_endpoint(monkeypatch=None):
    import main

    captured = {}

    async def fake_get_async(path, params=None):
        captured["path"] = path
        captured["params"] = params or {}
        return {"products": [{"code": "1", "product_name": "Oat milk"}], "count": 1}

    orig_get = getattr(main, "_openfoodfacts_get_async", None)
    if monkeypatch is not None:
        monkeypatch.setattr(main, "_openfoodfacts_get_async", fake_get_async)
    else:
        main._openfoodfacts_get_async = fake_get_async

    try:
        result = asyncio.run(main._search_foods("oat milk", 5))
        assert captured["path"] == "/cgi/search.pl"
        assert captured["params"]["search_terms"] == "oat milk"
        assert captured["params"]["json"] == 1
        assert result["count"] == 1
        assert result["products"][0]["name"] == "Oat milk"
    finally:
        if monkeypatch is None and orig_get is not None:
            main._openfoodfacts_get_async = orig_get


if __name__ == "__main__":
    test_search_foods_uses_cgi_fulltext_endpoint()
    print("test_search_endpoint PASSED")
