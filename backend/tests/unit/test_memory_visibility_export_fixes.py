"""Regression: memory visibility / export / locked-preview fixes (QA PRs 11431/11433)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from tests.unit.test_memory_service_parity import _load_memory_service, _sample_memory_dict


@pytest.fixture
def service_mod(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "read")
    return _load_memory_service(monkeypatch)


def test_truncate_locked_preview_only_when_locked(service_mod):
    unlocked = service_mod.MemoryDB.model_validate(
        {**_sample_memory_dict("u1"), "is_locked": False, "content": "x" * 120}
    )
    locked = service_mod.MemoryDB.model_validate({**_sample_memory_dict("l1"), "is_locked": True, "content": "y" * 120})

    assert service_mod.truncate_locked_memory_preview(unlocked).content == "x" * 120
    preview = service_mod.truncate_locked_memory_preview(locked).content
    assert preview.endswith("...")
    assert len(preview) == 73
    assert preview[:70] == "y" * 70


def test_historical_adapt_logs_sanitized_validation_error(service_mod, monkeypatch, caplog):
    secret = "SUPER_SECRET_MEMORY_CONTENT_DO_NOT_LOG"
    raw = _sample_memory_dict("bad-1")
    raw["content"] = secret

    def _raise_validation(_raw, *, include_locked_content=False):
        from pydantic import BaseModel

        class _Probe(BaseModel):
            content: str

        _Probe.model_validate({"content": {"nested": secret}})

    monkeypatch.setattr(
        service_mod.HistoricalMemoryAdapter,
        "_historical_memory",
        staticmethod(_raise_validation),
    )

    with caplog.at_level("WARNING"):
        record = service_mod.HistoricalMemoryAdapter._adapt("uid-test", raw)

    assert record is None
    joined = "\n".join(r.message for r in caplog.records)
    assert secret not in joined
    assert "bad-1" in joined
    assert "Skipping malformed historical memory" in joined


def test_historical_read_compensates_for_skipped_malformed_rows(service_mod, monkeypatch):
    good = [_sample_memory_dict(f"good-{i}") for i in range(3)]
    for index, row in enumerate(good):
        stamp = datetime(2026, 1, 3 - index, tzinfo=timezone.utc).isoformat()
        row["updated_at"] = stamp
        row["created_at"] = stamp
        row["content"] = f"good-{index}"

    bad = _sample_memory_dict("bad")
    bad["id"] = ""  # adapter skips identity-less rows
    # First page: two good + one skipped. Compensation must pull the third good.
    pages = {
        0: [good[0], bad, good[1]],
        3: [good[2]],
    }

    def get_memories(_uid, limit, offset, **_kwargs):
        return list(pages.get(offset, []))[:limit]

    monkeypatch.setattr(service_mod.memories_db, "get_memories", get_memories)
    adapter = service_mod.HistoricalMemoryAdapter(db_client=object())

    page = adapter.read("uid-test", limit=3, offset=0)

    assert [record.memory.id for record in page] == ["good-0", "good-1", "good-2"]


def test_iter_export_memories_streams_without_materializing_history(service_mod, monkeypatch):
    service = service_mod.MemoryService(db_client=MagicMock())
    monkeypatch.setattr(service_mod, "iter_authoritative_product_memory_items", lambda **_kwargs: iter(()))
    historical = [
        service_mod.HistoricalMemoryRecord(
            memory=service_mod.MemoryDB.model_validate(_sample_memory_dict(f"h-{i}")),
            locator=service_mod.MemoryLocator("uid-test", "legacy", f"h-{i}"),
        )
        for i in range(3)
    ]
    seen_pages: list[int] = []

    def fake_iter(_uid, *, page_size=500):
        seen_pages.append(page_size)
        yield from historical

    service.history.iter_all_live = fake_iter
    service.canonical_statuses = MagicMock(return_value={})

    streamed = []
    for memory in service.iter_export_memories("uid-test", page_size=2):
        streamed.append(memory.id)
        if len(streamed) == 1:
            assert seen_pages == [2]

    assert streamed == ["h-0", "h-1", "h-2"]


def test_developer_list_requests_pending_processing(monkeypatch):
    """Just-created required-processing memories must be requested on list."""
    from tests.unit import test_dev_api_memories_pagination as page_mod

    client, memory_service = page_mod._build([], monkeypatch)
    assert client.get("/v1/dev/user/memories").status_code == 200
    assert memory_service.read.call_args.kwargs.get("include_pending_processing") is True
