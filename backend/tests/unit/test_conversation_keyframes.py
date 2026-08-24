from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services import conversation_keyframes


class _Screen:
    def __init__(self, identifier: str, **data):
        self.id = identifier
        self.data = data

    def to_dict(self):
        return self.data


def _screen(index: int, *, eligible: bool = True, local_id: str | None = None):
    return _Screen(
        f"opaque-storage-{index}",
        timestamp=f"2026-08-24 10:{index // 60:02d}:{index % 60:02d}.000",
        appName="Editor",
        windowTitle="Notes",
        captureEligible=eligible,
        localScreenshotId=local_id or str(index),
        deviceRetentionSeconds=86400,
    )


def test_exact_500_candidates_select_latest_authoritative_local_id():
    selected = conversation_keyframes._select_screen_winner([_screen(index) for index in range(500)])
    assert selected is not None
    winner, local_id, retention = selected
    assert winner.frame_id == "opaque-storage-499"
    assert local_id == "499"
    assert retention == 86400


def test_over_500_newest_page_converges_and_rejects_local_exclusion_attestation():
    rows = [_screen(501, eligible=False), _screen(500, local_id="77")] + [_screen(index) for index in range(499)]
    selected = conversation_keyframes._select_screen_winner(rows)
    assert selected is not None
    winner, local_id, _ = selected
    assert winner.frame_id == "opaque-storage-500"
    assert local_id == "77"


def test_over_500_ineligible_prefix_pages_to_older_eligible_frame():
    rows = [_screen(index, eligible=False) for index in range(600, 100, -1)] + [_screen(100, local_id="9")]

    def fetch(cursor):
        start = 0 if cursor is None else rows.index(cursor) + 1
        return rows[start : start + 501]

    selected, exhausted = conversation_keyframes._select_screen_pages(fetch)
    assert exhausted is False
    assert selected is not None
    winner, local_id, _ = selected
    assert winner.frame_id == "opaque-storage-100"
    assert local_id == "9"


def test_normal_selection_is_one_query_and_corrupt_prefix_has_hard_5k_bound():
    normal_calls = []
    selected, exhausted = conversation_keyframes._select_screen_pages(
        lambda cursor: normal_calls.append(cursor) or [_screen(1)]
    )
    assert selected is not None and exhausted is False and len(normal_calls) == 1

    corrupt_calls = []
    corrupt_page = [_screen(index, eligible=False) for index in range(501)]
    selected, exhausted = conversation_keyframes._select_screen_pages(
        lambda cursor: corrupt_calls.append(cursor) or corrupt_page
    )
    assert selected is None and exhausted is True
    assert len(corrupt_calls) == 10


def test_password_surface_is_fail_closed_even_if_client_attests_eligible():
    row = _screen(1)
    row.data["appName"] = "1Password"
    assert conversation_keyframes._select_screen_winner([row]) is None


def test_missing_local_capture_attestation_is_fail_closed():
    row = _screen(1)
    row.data.pop("captureEligible")
    assert conversation_keyframes._select_screen_winner([row]) is None


def test_finalization_retry_cannot_regress_requested_job(monkeypatch):
    class Snapshot:
        def __init__(self, data):
            self.exists = data is not None
            self._data = data

        def to_dict(self):
            return self._data

    class Ref:
        def __init__(self):
            self.data = None

        def get(self, transaction=None):
            return Snapshot(self.data)

    ref = Ref()

    class Client:
        def collection(self, _name):
            return self

        def document(self, _name):
            return self if _name == "uid" else ref

        def transaction(self):
            class Transaction:
                @staticmethod
                def create(target, data):
                    target.data = dict(data)

            return Transaction()

    monkeypatch.setattr(conversation_keyframes.firestore, "transactional", lambda fn: fn)
    conversation = SimpleNamespace(
        id="conversation-1",
        source=SimpleNamespace(value="desktop"),
        started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        finished_at=datetime.now(timezone.utc),
        client_device_id="mac-1",
    )
    assert conversation_keyframes.ensure_conversation_keyframe_job("uid", conversation, firestore_client=Client())
    assert ref.data["expires_at"] == conversation.finished_at + timedelta(days=7)
    ref.data["state"] = "requested"
    assert conversation_keyframes.ensure_conversation_keyframe_job("uid", conversation, firestore_client=Client())
    assert ref.data["state"] == "requested"


def test_expired_keyframe_cleanup_deletes_only_bounded_operational_jobs():
    deleted = []

    class Snapshot:
        def __init__(self, identifier):
            self.reference = SimpleNamespace(delete=lambda: deleted.append(identifier))

    class Query:
        def collection(self, _name):
            return self

        def document(self, _name):
            return self

        def where(self, *, filter):
            assert filter.field_path == "expires_at"
            return self

        def limit(self, value):
            assert value == 2
            return self

        def stream(self):
            return [Snapshot("pending-job"), Snapshot("requested-job")]

    count = conversation_keyframes.prune_expired_conversation_keyframe_jobs(
        "uid",
        firestore_client=Query(),
        now=datetime(2026, 8, 24, tzinfo=timezone.utc),
        limit=2,
    )

    assert count == 2
    assert deleted == ["pending-job", "requested-job"]
