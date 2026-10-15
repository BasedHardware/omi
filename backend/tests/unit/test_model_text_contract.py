"""Ratchet: model-facing modules format times only through ``utils.model_text``.

An ad-hoc ``strftime``/``isoformat`` in a chat or MCP tool is how an unlabelled UTC wall clock
reached the model and turned a 2:18 PM event into "7:18 a.m." (see ``utils/model_text.py``).

A line is exempt when it carries ``# not-model-facing: <reason>``: API request parameters,
client payloads, log lines. ``BASELINE`` holds the pre-existing calls per file; it may only go
down. When you remove calls, lower the number in the same change.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

MODEL_FACING_GLOBS = (
    'utils/retrieval/tools/*.py',
    'utils/retrieval/tool_services/*.py',
    'utils/conversations/render.py',
    'utils/conversations/transcript_chunks.py',
    'utils/conversations/mcp_transcript_search.py',
    'routers/tools.py',
    'utils/llm/chat.py',
)

_CALL = re.compile(r'\.(strftime|isoformat)\(')
_EXEMPT = '# not-model-facing:'

BASELINE = {
    'routers/tools.py': 3,
    'utils/conversations/render.py': 6,
    'utils/conversations/transcript_chunks.py': 1,
    'utils/llm/chat.py': 4,
    'utils/retrieval/tool_services/action_items.py': 10,
    'utils/retrieval/tool_services/conversations.py': 3,
    'utils/retrieval/tool_services/memories.py': 4,
    'utils/retrieval/tools/action_item_tools.py': 17,
    'utils/retrieval/tools/apple_health_tools.py': 6,
    'utils/retrieval/tools/calendar_tools.py': 28,
    'utils/retrieval/tools/conversation_jit.py': 1,
    'utils/retrieval/tools/conversation_tools.py': 7,
    'utils/retrieval/tools/edit_tools.py': 1,
    'utils/retrieval/tools/entity_timeline_tools.py': 2,
    'utils/retrieval/tools/gmail_tools.py': 1,
    'utils/retrieval/tools/knowledge_ledger_tools.py': 1,
    'utils/retrieval/tools/memory_tools.py': 6,
    'utils/retrieval/tools/screen_activity_tools.py': 1,
}


def _counts():
    counts = {}
    for pattern in MODEL_FACING_GLOBS:
        for path in sorted(BACKEND.glob(pattern)):
            rel = path.relative_to(BACKEND).as_posix()
            n = sum(
                1
                for line in path.read_text(encoding='utf-8').splitlines()
                if _CALL.search(line) and _EXEMPT not in line
            )
            if n:
                counts[rel] = n
    return counts


def test_no_new_adhoc_time_formatting_in_model_facing_modules():
    grown = {f: (n, BASELINE.get(f, 0)) for f, n in _counts().items() if n > BASELINE.get(f, 0)}
    assert not grown, (
        'New strftime/isoformat in model-facing modules (file: (now, allowed)). Render through '
        'utils.model_text, or mark a non-model line with "# not-model-facing: <reason>": '
        f'{grown}'
    )


def test_baseline_is_tightened_when_calls_are_removed():
    counts = _counts()
    stale = {f: (counts.get(f, 0), allowed) for f, allowed in BASELINE.items() if counts.get(f, 0) < allowed}
    assert not stale, f'Lower BASELINE to the current counts (file: (now, baseline)): {stale}'
