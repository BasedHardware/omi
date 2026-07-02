"""Unit tests for the clone benchmark (Nik's "benchmark against your own past decisions")."""

from contextlib import contextmanager
from pathlib import Path
import sys
import types

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _install_module(name, **attrs):
    module = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    if '.' in name:
        parent_name, child_name = name.rsplit('.', 1)
        parent = sys.modules.setdefault(parent_name, types.ModuleType(parent_name))
        if not hasattr(parent, '__path__'):
            parent.__path__ = [str(BACKEND_DIR / parent_name.replace('.', '/'))]
        setattr(parent, child_name, module)
    sys.modules[name] = module
    return module


class _Message:
    def __init__(self, content):
        self.content = content


@contextmanager
def _track_usage(_uid, _feature):
    yield


_install_module('database.chat', get_messages=lambda *_a, **_k: [])
_install_module('database.memories', get_memories=lambda *_a, **_k: [])
_install_module('database.apps', get_user_persona_by_uid=lambda _uid: None)
_install_module('langchain_core.messages', HumanMessage=_Message, SystemMessage=_Message)
_install_module('utils.llm.clients', get_llm=lambda _feature: None)
_install_module(
    'utils.llm.usage_tracker', Features=types.SimpleNamespace(REPLY_DRAFT='reply_draft'), track_usage=_track_usage
)
_install_module('utils.users', get_user_display_name=lambda _uid, default='Someone': default)

from models.clone import (  # noqa: E402
    CloneBenchmarkItem,
    CloneBenchmarkRequest,
    CloneBenchmarkSample,
    CloneContextSummary,
    CloneMatchJudgment,
    CloneReplyResponse,
)
from utils.llm import clone_benchmark  # noqa: E402


def test_aggregate_computes_match_rate():
    items = [
        CloneBenchmarkItem(
            incoming_message='a', actual_reply='x', generated_reply='x', match=True, score=0.9, reason=''
        ),
        CloneBenchmarkItem(
            incoming_message='b', actual_reply='y', generated_reply='z', match=False, score=0.3, reason=''
        ),
        CloneBenchmarkItem(
            incoming_message='c', actual_reply='w', generated_reply='w', match=True, score=1.0, reason=''
        ),
    ]
    result = clone_benchmark.aggregate_benchmark(items)
    assert result.total == 3
    assert result.matched == 2
    assert abs(result.match_rate - 2 / 3) < 1e-9
    assert abs(result.average_score - (0.9 + 0.3 + 1.0) / 3) < 1e-9


def test_aggregate_empty():
    result = clone_benchmark.aggregate_benchmark([])
    assert result.total == 0
    assert result.match_rate == 0.0


def test_benchmark_clone_flow(monkeypatch):
    def fake_draft(_uid, request):
        return CloneReplyResponse(
            draft=f'drafted:{request.incoming_message}',
            confidence=0.8,
            action='review',
            action_reason='',
            used_context=CloneContextSummary(memories_used=0, thread_messages_used=0, persona_used=False),
        )

    monkeypatch.setattr(clone_benchmark, 'draft_on_behalf_reply', fake_draft)
    # Judge: it's a match when the user's actual reply said "yes".
    monkeypatch.setattr(
        clone_benchmark,
        '_judge_match',
        lambda incoming, actual, generated: CloneMatchJudgment(
            match=('yes' in actual), score=1.0 if 'yes' in actual else 0.0, reason=''
        ),
    )
    request = CloneBenchmarkRequest(
        samples=[
            CloneBenchmarkSample(incoming_message='dinner?', actual_reply='yes lets go'),
            CloneBenchmarkSample(incoming_message='call?', actual_reply='no cant right now'),
        ]
    )
    result = clone_benchmark.benchmark_clone('uid', request)
    assert result.total == 2
    assert result.matched == 1
    assert abs(result.match_rate - 0.5) < 1e-9
    assert result.items[0].generated_reply == 'drafted:dinner?'
