"""Crossref payload shapes must not crash a tool or silently truncate a value.

The Crossref REST API returns `title` as an array on most works but as a plain string on some
records, and any element of `message.items` can be something other than an object. `date-parts`
can likewise arrive as a string. The chat tools assumed one shape each time, so one unusual
record either raises inside the handler or produces a wrong value that reaches the user with no
error at all: `"Sleep and Memory"[0]` is `"S"`, and `"2020"[0]` is `"2"`.

These tests drive the real `search_crossref_works`, `get_crossref_work` and
`search_crossref_by_author` handlers with `crossref_get` patched to a fixed payload, so the same
assertions fail against the unpatched source for the reason the issue describes. Hermetic:
httpx/fastapi/pydantic are stubbed, no network, no sleeps, stdlib only.
"""

import asyncio
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))


def _stub(name, **attrs):
    if name not in sys.modules:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


class _Model:
    """Minimal stand-in for a pydantic model: accepts keyword fields."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _App:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: (lambda f: f)


def _load():
    if "crossref_main" in sys.modules:
        return sys.modules["crossref_main"]
    _stub("httpx", AsyncClient=object)
    _stub("fastapi", FastAPI=_App, Query=lambda *a, **k: None,
          HTTPException=type("HTTPException", (Exception,), {}))
    _stub("pydantic", BaseModel=_Model, Field=lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location("crossref_main", os.path.join(HERE, "main.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["crossref_main"] = module
    spec.loader.exec_module(module)
    return module


def _run(handler, payload, results):
    """Drive one handler with crossref_get patched to a fixed Crossref payload."""
    module = _load()

    async def fake_get(path, params):
        return results

    module.crossref_get = fake_get
    return asyncio.run(handler(payload))


def _search(query="sleep memory", items=None):
    module = _load()
    payload = module.SearchWorksInput(query=query, max_results=5)
    return _run(module.search_crossref_works, payload,
                {"message": {"items": items if items is not None else []}})


def test_string_title_is_not_truncated_to_its_first_character():
    """Crossref returns a bare string title on some records."""
    response = _search(items=[{"title": "Sleep and Memory", "DOI": "10.1/x"}])
    assert "Sleep and Memory" in (response.result or ""), response.result
    assert "\n1. S " not in (response.result or ""), f"truncated: {response.result}"


def test_list_title_still_reads_its_first_entry():
    response = _search(items=[{"title": ["Sleep and Memory", "alt"], "DOI": "10.1/x"}])
    assert "Sleep and Memory" in (response.result or ""), response.result


def test_scalar_title_falls_back_instead_of_raising():
    response = _search(items=[{"title": 42, "DOI": "10.1/x"}])
    assert (response.result or "").startswith("Top 1"), response.result
    assert "Untitled" in (response.result or ""), response.result


def test_item_without_a_title_falls_back():
    response = _search(items=[{"DOI": "10.1/x"}])
    assert "Untitled" in (response.result or ""), response.result


def test_scalar_issued_date_yields_the_year():
    response = _search(items=[{"title": ["T"], "issued": "2020"}])
    assert "(2020)" in (response.result or ""), response.result


def test_scalar_date_parts_yields_the_year_not_its_first_digit():
    response = _search(items=[{"title": ["T"], "issued": {"date-parts": "2020"}}])
    assert "(2020)" in (response.result or ""), response.result


def test_well_formed_date_parts_still_work():
    response = _search(items=[{"title": ["T"], "issued": {"date-parts": [[2019, 3, 1]]}}])
    assert "(2019)" in (response.result or ""), response.result


CASES = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    failures = 0
    for case in CASES:
        try:
            case()
            print(f"PASS {case.__name__}")
        except Exception as e:
            failures += 1
            print(f"FAIL {case.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
