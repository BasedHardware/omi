#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."
python3 desktop/macos/scripts/context-bucket-benchmark.py

python3 - <<'PY'
import importlib.util
import io
from pathlib import Path
import sys
import types
from unittest.mock import patch
from urllib import error

path = Path("desktop/macos/scripts/context-bucket-benchmark.py")
spec = importlib.util.spec_from_file_location("context_bucket_benchmark", path)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

case = {
    "id": "synthetic-text-output",
    "expectedAction": "notify",
    "allowedDecisions": ["suggest", "resurface"],
    "forbiddenOutputTerms": ["forbidden phrase"],
    "synthetic": {
        "bucket": {"id": "bucket-1", "version": 1, "notifyWorthiness": 1, "entries": []},
        "frames": [
            {
                "capturedAt": "2026-08-13T16:00:00Z",
                "appName": "SyntheticEditor",
                "windowTitle": "Synthetic window",
            }
        ],
        "tasks": [],
    },
}
envelope = {
    "ok": True,
    "result": {
        "detail": {
            "decision": "suggest",
            "model": "synthetic-model",
            "latency_ms": "1",
            "title": "Synthetic title",
            "message": "Synthetic message",
            "reasoning": "Synthetic reasoning",
        }
    },
}


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        import json

        return json.dumps(envelope).encode()


token_module = types.ModuleType("automation_token_lib")
token_module.automation_token = lambda _port: "synthetic-token"
sys.modules["automation_token_lib"] = token_module
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    terse = benchmark.invoke_case(case, 47910)
    detailed = benchmark.invoke_case(case, 47910, include_text=True)

assert "title" not in terse and "message" not in terse and "reasoning" not in terse
assert detailed["title"] == "Synthetic title"
assert detailed["message"] == "Synthetic message"
assert detailed["reasoning"] == "Synthetic reasoning"
assert detailed["polarity_matched"] is True
assert detailed["decision_matched"] is True
assert detailed["forbidden_output_matched"] is False
assert detailed["forbidden_terms_matched"] == []

leaking_case = {**case, "forbiddenOutputTerms": ["synthetic MESSAGE"]}
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    leaking = benchmark.invoke_case(leaking_case, 47910)
assert leaking["polarity_matched"] is True
assert leaking["decision_matched"] is True
assert leaking["forbidden_output_matched"] is True
assert leaking["forbidden_terms_matched"] == ["synthetic MESSAGE"]
assert leaking["matched"] is False

wrong_type_case = {**case, "allowedDecisions": ["resurface"]}
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    wrong_type = benchmark.invoke_case(wrong_type_case, 47910)
assert wrong_type["polarity_matched"] is True
assert wrong_type["decision_matched"] is False
assert wrong_type["matched"] is False

envelope["result"]["detail"]["decision"] = "unexpected"
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    try:
        benchmark.invoke_case(case, 47910)
    except RuntimeError as exc:
        assert str(exc) == "synthetic-text-output: probe returned invalid decision"
    else:
        raise AssertionError("unknown director decisions must fail closed")
envelope["result"]["detail"]["decision"] = "suggest"

with patch.object(
    benchmark.request,
    "urlopen",
    side_effect=error.HTTPError("http://127.0.0.1", 400, "Bad Request", None, None),
):
    try:
        benchmark.invoke_case(case, 47910)
    except RuntimeError as exc:
        assert str(exc) == "synthetic-text-output: probe returned HTTP 400"
    else:
        raise AssertionError("HTTP probe failure must carry the scenario ID")

stable_error_body = io.BytesIO(
    b'{"ok":false,"error":"action failed: proactive_http_error status=429"}'
)
with patch.object(
    benchmark.request,
    "urlopen",
    side_effect=error.HTTPError("http://127.0.0.1", 400, "Bad Request", None, stable_error_body),
):
    try:
        benchmark.invoke_case(case, 47910)
    except RuntimeError as exc:
        assert str(exc) == (
            "synthetic-text-output: probe returned HTTP 400 (proactive_http_error status=429)"
        )
    else:
        raise AssertionError("stable proactive failure must survive the bridge envelope")
PY
