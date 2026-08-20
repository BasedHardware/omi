#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."
python3 desktop/macos/scripts/context-bucket-benchmark.py

python3 - <<'PY'
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch
from urllib import error

path = Path("desktop/macos/scripts/context-bucket-benchmark.py")
spec = importlib.util.spec_from_file_location("context_bucket_benchmark", path)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

fixture = json.loads(Path("desktop/macos/e2e/fixtures/context-bucket-proactivity-benchmark.json").read_text())
material_case = next(case for case in fixture["cases"] if case["id"] == "worthy-material-change-no-commitment")
assert set(material_case["allowedDecisions"]) == {"insight", "suggest"}
assert material_case["forbiddenOutputTerms"] == [
    "task_candidate",
    "assigned owner: Alex",
    "due tomorrow",
    "due at 17:00",
]
assert json.loads(benchmark.map_case(material_case)["tasks"]) == []

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
assert detailed["failure_reasons"] == []
assert detailed["referent_named"] is None
assert detailed["referent_hits"] == []

# A case that declares referentTokens fails when the user-visible text names none
# of them, and `reasoning` -- which the user never sees -- cannot rescue it.
named_case = {**case, "referentTokens": ["Synthetic title"]}
unnamed_case = {**case, "referentTokens": ["#4821", "nimbus-labs/ingest-suite"]}
reasoning_only_case = {**case, "referentTokens": ["Synthetic reasoning"]}
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    named = benchmark.invoke_case(named_case, 47910)
    unnamed = benchmark.invoke_case(unnamed_case, 47910)
    reasoning_only = benchmark.invoke_case(reasoning_only_case, 47910)
assert named["referent_named"] is True
assert named["referent_hits"] == ["Synthetic title"]
assert named["failure_reasons"] == []
assert named["matched"] is True
assert unnamed["referent_named"] is False
assert unnamed["failure_reasons"] == ["unnamed_referent"]
assert unnamed["matched"] is False
assert reasoning_only["referent_named"] is False
assert reasoning_only["failure_reasons"] == ["unnamed_referent"]

# Silence carries no user-visible text, so the criterion does not apply to it.
envelope["result"]["detail"]["decision"] = "silence"
silent_case = {**unnamed_case, "expectedAction": "silence", "allowedDecisions": ["silence"]}
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    silent = benchmark.invoke_case(silent_case, 47910)
assert silent["failure_reasons"] == []
assert silent["matched"] is True
envelope["result"]["detail"]["decision"] = "suggest"

referent_ids = {c["id"] for c in fixture["cases"] if c["id"].startswith("referent-")}
assert referent_ids <= benchmark.DIRECTOR_CASES
assert benchmark.REFERENT_CASES == referent_ids
for referent_case in (c for c in fixture["cases"] if c["id"] in referent_ids):
    # The one deliberate exception is the control whose context supplies no handle.
    if referent_case["id"] == "referent-no-identifier":
        assert referent_case["referentTokens"] == []
        continue
    assert referent_case["referentTokens"], referent_case["id"]

leaking_case = {**case, "forbiddenOutputTerms": ["synthetic MESSAGE"]}
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    leaking = benchmark.invoke_case(leaking_case, 47910)
assert leaking["polarity_matched"] is True
assert leaking["decision_matched"] is True
assert leaking["forbidden_output_matched"] is True
assert leaking["forbidden_terms_matched"] == ["synthetic MESSAGE"]
assert leaking["failure_reasons"] == ["forbidden_output"]
assert leaking["matched"] is False

wrong_type_case = {**case, "allowedDecisions": ["resurface"]}
with patch.object(benchmark.request, "urlopen", return_value=Response()):
    wrong_type = benchmark.invoke_case(wrong_type_case, 47910)
assert wrong_type["polarity_matched"] is True
assert wrong_type["decision_matched"] is False
assert wrong_type["failure_reasons"] == ["decision"]
assert wrong_type["matched"] is False

horizon_case = {
    **case,
    "synthetic": {
        **case["synthetic"],
        "tasks": [
            {"description": "overdue", "status": "open", "dueAt": "2026-08-13T15:00:00Z"},
            {"description": "near", "status": "open", "dueAt": "2026-08-15T16:00:00Z"},
            {"description": "far", "status": "open", "dueAt": "2026-08-15T16:00:01Z"},
            {"description": "undated", "status": "open"},
            {"description": "done", "status": "completed", "dueAt": "2026-08-13T17:00:00Z"},
        ],
    },
}
mapped_tasks = __import__("json").loads(benchmark.map_case(horizon_case)["tasks"])
assert [task["description"] for task in mapped_tasks] == ["overdue", "near", "undated", "far"]

many_tasks_case = {
    **horizon_case,
    "synthetic": {
        **horizon_case["synthetic"],
        "tasks": [
            {"id": f"task-{index:02d}", "description": f"task-{index:02d}", "status": "open"}
            for index in range(25)
        ],
    },
}
assert len(__import__("json").loads(benchmark.map_case(many_tasks_case)["tasks"])) == 20

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
