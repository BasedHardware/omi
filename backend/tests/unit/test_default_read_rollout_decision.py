from utils.memory.default_read_rollout import (
    GLOBAL_READ_GATE_PATH,
    MemoryReadDecision,
    normalize_default_read_rollout_decision,
    normalize_global_read_gate,
    read_default_read_rollout,
)


class _Snapshot:
    def __init__(self, data, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, timeout=None):
        del timeout
        self.db.reads.append(self.path)
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self.db.docs[self.path])


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.reads = []

    def document(self, path):
        return _Document(self, path)


def _normalize(data, consumer="omi_chat"):
    return normalize_default_read_rollout_decision(
        uid="u1", source_path="users/u1/memory_control/state", consumer=consumer, data=data
    )


def test_missing_control_state_uses_universal_memory_without_backfill():
    db = _FirestoreFake()
    decision = read_default_read_rollout(uid="u1", db_client=db, consumer="omi_chat")
    assert decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert decision.app_has_default_memory_grant is True
    assert decision.rollout_capabilities.memory_reads_enabled is True
    assert decision.rollout_capabilities.legacy_reads_authoritative is False
    assert db.reads == ["users/u1/memory_control/state"]


def test_old_rollout_stage_fields_cannot_change_universal_product_authority():
    denied_stage = _normalize(
        {
            "uid": "u1",
            "schema_version": 1,
            "mode": "off",
            "writes_blocked": True,
            "fallback_projection_ready": False,
            "stage_gates": {"read": "blocked"},
        }
    )
    assert denied_stage.read_decision == MemoryReadDecision.USE_MEMORY
    assert denied_stage.rollout_capabilities.mode.value == "read"


def test_explicit_consumer_grant_false_is_preserved():
    decision = _normalize({"uid": "u1", "schema_version": 1, "grants": {"omi_chat": {"default_memory": False}}})
    assert decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert decision.fallback_reason == "missing_chat_default_memory_grant"


def test_malformed_grants_uid_and_generation_fail_closed():
    cases = [
        {"uid": "other"},
        {"uid": "u1", "grants": []},
        {"uid": "u1", "grants": {"omi_chat": {"default_memory": "true"}}},
        {"uid": "u1", "account_generation": -1},
    ]
    for data in cases:
        assert _normalize(data).read_decision == MemoryReadDecision.DENY_MEMORY


def test_global_read_gate_remains_deployment_wide_and_fail_closed():
    assert normalize_global_read_gate(None).read_decision == MemoryReadDecision.DENY_MEMORY
    assert normalize_global_read_gate({"memory_reads_enabled": True, "kill_switch_active": True}).read_decision == (
        MemoryReadDecision.DENY_MEMORY
    )
    open_gate = normalize_global_read_gate({"memory_reads_enabled": True, "kill_switch_active": False})
    assert open_gate.source_path == GLOBAL_READ_GATE_PATH
    assert open_gate.read_decision == MemoryReadDecision.USE_MEMORY


def test_control_state_timeout_fails_closed_without_legacy_fallback():
    class _TimedOutDocument:
        def get(self, **_kwargs):
            raise TimeoutError("control-state read timed out")

    class _TimedOutDb:
        def document(self, _path):
            return _TimedOutDocument()

    decision = read_default_read_rollout(uid="u1", db_client=_TimedOutDb(), consumer="omi_chat")

    assert decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert decision.reason == "memory_control_read_failed"
    assert decision.rollout_capabilities.legacy_reads_authoritative is False
