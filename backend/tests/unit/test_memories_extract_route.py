"""Return-only memory-log extract uses the managed memories feature."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import memories as memories_router
from utils.llm.memories import MemoryLogExtraction

UID = 'uid-memories-extract'


def test_extract_memory_log_returns_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_extract(uid, text, **kwargs):
        calls['uid'] = uid
        calls['text'] = text
        calls['kwargs'] = kwargs
        return MemoryLogExtraction(memories=['Likes coffee'], profile='Coffee person.')

    import utils.llm.memories as memories_llm

    monkeypatch.setattr(memories_llm, 'extract_memory_log_from_text', fake_extract)

    response = memories_router.extract_memory_log(
        memories_router.ExtractMemoryLogRequest(
            text='I like coffee',
            text_source='chatgpt',
            existing_memories=['Lives in NYC'],
        ),
        uid=UID,
    )

    assert response.memories == ['Likes coffee']
    assert response.profile == 'Coffee person.'
    assert calls['uid'] == UID
    assert calls['text'] == 'I like coffee'
    assert calls['kwargs']['text_source'] == 'chatgpt'
    assert calls['kwargs']['existing_memories'] == ['Lives in NYC']


def test_extract_memory_log_fails_closed_when_extractor_returns_none(monkeypatch):
    import utils.llm.memories as memories_llm

    monkeypatch.setattr(memories_llm, 'extract_memory_log_from_text', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        memories_router.extract_memory_log(
            memories_router.ExtractMemoryLogRequest(text='something memorable'),
            uid=UID,
        )
    assert exc.value.status_code == 502
