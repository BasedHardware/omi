"""Contract tests for execute_persona_chat_stream's LangSmith wiring.

Code-review sub-agent on PR #8531 caught a cubic follow-up: the
previous fix wired the LangChainTracer but did NOT pass run_id via
RunnableConfig. LangChainTracer.__init__ silently swallows the
run_id kwarg, so the run_id stored on callback_data['langsmith_run_id']
would never match the UUID of the actual LangSmith trace \u2014 making
submit_langsmith_feedback() fail with 404 against any LangSmith project.

These tests pin the contract by introspecting the source code so the
test stays fast and dependency-free (no langchain import required).

If a future refactor reintroduces the bug, these tests fail with a
clear message before the regression lands.
"""

import os
import re
from pathlib import Path

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel_path: str) -> str:
    return Path(os.path.join(_BACKEND, rel_path)).read_text()


def _extract_function(src: str, name: str) -> str:
    """Return the body of the named `async def` (greedy until next
    top-level `async def` / `def` / `class`)."""
    m = re.search(
        rf"^(async )?def {re.escape(name)}\(.*?(?=^\s*(async )?def\s+\w+|^class\s+\w+|\Z)",
        src,
        re.MULTILINE | re.DOTALL,
    )
    assert m, f"could not locate function {name}"
    return m.group(0)


def _extract_nested_dicts_after(src: str, marker: str) -> list:
    """Find every `marker:` followed by a `{...}` dict (nested braces
    handled). Returns the dict-string for each match."""
    out = []
    i = 0
    while True:
        idx = src.find(marker, i)
        if idx == -1:
            break
        # find the opening '{' after the marker
        brace = src.find("{", idx)
        if brace == -1:
            i = idx + 1
            continue
        # walk forward counting braces
        depth = 0
        j = brace
        while j < len(src):
            ch = src[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    out.append(src[brace : j + 1])
                    break
            j += 1
        i = j + 1 if j < len(src) else len(src)
    return out


class TestExecutePersonaChatStreamLangSmithContract:
    """Verify run_id is plumbed via RunnableConfig, not just the tracer constructor."""

    def test_runnable_config_carries_run_id(self):
        """P2 (cubic + code-review follow-up): the LangChainTracer
        constructor silently swallows run_id (verified: __init__ only
        accepts example_id, project_name, client, tags, kwargs). The
        astream() call must therefore pass run_id via RunnableConfig
        so the actual trace gets stamped with the same UUID that's
        stored on callback_data['langsmith_run_id']. Otherwise
        submit_langsmith_feedback() fails with 404 against any
        LangSmith project."""
        src = _read("utils/retrieval/graph.py")
        fn = _extract_function(src, "execute_persona_chat_stream")

        # The RunnableConfig dict must contain BOTH 'callbacks' (so the
        # tracer is attached) AND 'run_id' (so the trace gets stamped
        # with the stored UUID).
        # Use a brace-counting scan because the inner dict may itself
        # contain braces (e.g. {callbacks: [...]}).
        config_dicts = _extract_nested_dicts_after(fn, '"config"')
        assert config_dicts, (
            "execute_persona_chat_stream must pass a 'config' dict to "
            "llm.astream() with both 'callbacks' and 'run_id' keys."
        )

        has_run_id = any("run_id" in d for d in config_dicts)
        has_callbacks = any("callbacks" in d for d in config_dicts)

        assert has_callbacks, "RunnableConfig must include 'callbacks' (tracer wiring)"
        assert has_run_id, (
            "RunnableConfig must include 'run_id' so the actual LangSmith "
            "trace gets stamped with the UUID stored on "
            "callback_data['langsmith_run_id']. Without this, "
            "submit_langsmith_feedback() will fail with 404 in production."
        )

    def test_no_phantom_run_id_when_api_key_missing(self):
        """When no API key is configured, callback_data must NOT carry
        a fabricated run_id \u2014 a phantom UUID would make
        submit_langsmith_feedback() attempt to attach feedback to a\n        non-existent trace and fail."""
        src = _read("utils/retrieval/graph.py")
        fn = _extract_function(src, "execute_persona_chat_stream")

        # The langsmith_run_id should be None when has_langsmith_api_key() is False
        assert re.search(
            r"langsmith_run_id\s*=\s*uuid\.uuid4\(\)\s+if\s+has_langsmith_api_key\(\)\s+else\s+None",
            fn,
        ), "langsmith_run_id must be conditional on has_langsmith_api_key()"

        # callback_data['langsmith_run_id'] must only be set when langsmith_run_id is truthy
        assert re.search(
            r"if callback_data is not None and langsmith_run_id is not None:",
            fn,
        ), (
            "callback_data['langsmith_run_id'] must only be set when "
            "langsmith_run_id is not None \u2014 prevents phantom run_ids "
            "from breaking feedback submission when no API key is configured."
        )

    def test_get_chat_tracer_callbacks_docstring_reflects_actual_contract(self):
        """The previous docstring claimed `run_id` was used 'for feedback
        attachment' but the implementation doesn't actually wire it.
        Either fix the docstring or fix the implementation. We fix the\n        docstring (RunnableConfig.run_id is the supported path).
        """
        from utils.observability.langsmith import get_chat_tracer_callbacks
        import inspect

        doc = inspect.getdoc(get_chat_tracer_callbacks) or ""
        assert "RunnableConfig" in doc or "config=" in doc, (
            "get_chat_tracer_callbacks docstring must explain that "
            "run_id is currently unused by the tracer constructor and "
            "callers must use RunnableConfig to pin the trace's run_id."
        )
