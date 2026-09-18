"""Regression test: a malformed element in the AI's score array must not discard the valid ones.

`calculate_iq_with_ai()` parses the model's reply and then calls `score.get(...)` on every
element of the resulting array. Nothing checks that an element is a mapping, and `int(iq)`
assumes `iq` is number-like. One non-object element (or one `iq: null`) raises, and the
surrounding `except Exception` swallows it -- so the whole batch's scores are dropped and
every person in that batch silently falls back to a random score instead of the score the
model actually returned. A stray element is indistinguishable from "the model produced
nothing", which is exactly why the failure is silent.

Hermetic: stubs the module's FastAPI/requests imports and drives the real
`calculate_iq_with_ai()` through a patched HTTP seam. No network, no sleeps, stdlib only.
"""

import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_LOADS = json.loads


def _stub(name, **attrs):
    if name not in sys.modules:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


class _Recorder:
    """Stands in for `requests.post`. `reply` is the raw body string to serve."""

    def __init__(self, reply):
        self.reply = reply

    def __call__(self, url, **kwargs):
        reply = self.reply

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return REAL_LOADS(reply)

        return _Response()


def _load_module():
    def _router(**kwargs):
        ns = types.SimpleNamespace()
        ns.get = lambda *a, **k: (lambda f: f)
        ns.post = lambda *a, **k: (lambda f: f)
        ns.on_event = lambda *a, **k: (lambda f: f)
        return ns

    class _App:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return lambda *a, **k: None

    _stub("fastapi", APIRouter=_router, FastAPI=_App,
          Query=lambda *a, **k: None, HTTPException=type("HTTPException", (Exception,), {}))
    # Register `fastapi.responses` as a real submodule so `from fastapi.responses import ...`
    # resolves without a package on disk.
    sys.modules["fastapi"].__path__ = []
    _stub("fastapi.responses", HTMLResponse=object, JSONResponse=object)
    sys.modules["fastapi"].responses = sys.modules["fastapi.responses"]
    _stub("uvicorn", run=lambda *a, **k: None)
    _stub("requests", post=lambda *a, **k: None, get=lambda *a, **k: None)

    spec = importlib.util.spec_from_file_location(
        "iq_rating_main", os.path.join(HERE, "main.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["iq_rating_main"] = module
    spec.loader.exec_module(module)
    return module


PEOPLE = {
    "alice": {"name": "Alice", "mention_count": 12, "context_snippets": ["Alice debugged the parser"]},
    "bob": {"name": "Bob", "mention_count": 11, "context_snippets": ["Bob reviewed the design"]},
}


def _drive(answer_text):
    """Run the real calculate_iq_with_ai against a controlled model reply."""
    module = _load_module()
    module.OPENAI_API_KEY = "test-key"
    module.requests.post = _Recorder(json.dumps({"choices": [{"message": {"content": answer_text}}]}))
    # Deterministic fallback keeps "used the model's score" distinguishable from "fell back".
    # The real function returns a bare int; calculate_iq_with_ai wraps it as {"iq": <int>}.
    module.calculate_iq_score_random = lambda person: -1
    import copy
    return module.calculate_iq_with_ai(copy.deepcopy(PEOPLE))


def test_valid_array_scores_every_person():
    scores = _drive('[{"name": "alice", "iq": 120}, {"name": "bob", "iq": 95}]')
    assert scores["alice"]["iq"] == 120, scores
    assert scores["bob"]["iq"] == 95, scores


def test_leading_non_object_element_keeps_the_valid_scores():
    scores = _drive('[1, {"name": "alice", "iq": 120}, {"name": "bob", "iq": 95}]')
    assert scores["alice"]["iq"] == 120, f"alice fell back to {scores['alice']}"
    assert scores["bob"]["iq"] == 95, f"bob fell back to {scores['bob']}"


def test_null_element_keeps_the_valid_scores():
    scores = _drive('[null, {"name": "alice", "iq": 120}]')
    assert scores["alice"]["iq"] == 120, f"alice fell back to {scores['alice']}"


def test_string_element_keeps_the_valid_scores():
    scores = _drive('["alice", {"name": "alice", "iq": 120}]')
    assert scores["alice"]["iq"] == 120, f"alice fell back to {scores['alice']}"


def test_null_iq_falls_back_without_losing_its_siblings():
    scores = _drive('[{"name": "alice", "iq": null}, {"name": "bob", "iq": 95}]')
    assert scores["bob"]["iq"] == 95, f"bob fell back to {scores['bob']}"


def test_iq_as_numeric_string_still_parses():
    scores = _drive('[{"name": "alice", "iq": "120"}]')
    assert scores["alice"]["iq"] == 120, scores


def test_iq_is_clamped_to_the_documented_range():
    scores = _drive('[{"name": "alice", "iq": 9000}]')
    assert scores["alice"]["iq"] == 160, scores


def test_no_scores_in_reply_falls_back_for_everyone():
    scores = _drive("no array here")
    assert scores["alice"]["iq"] == -1 and scores["bob"]["iq"] == -1, scores


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
