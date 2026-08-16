from __future__ import annotations

import pytest

from utils.memory import promotion_flex


class _Snapshot:
    def __init__(self, payload):
        self.exists = payload is not None
        self._payload = payload

    def to_dict(self):
        return self._payload


class _Db:
    def __init__(self, payload):
        self.payload = payload
        self.reads = 0

    def document(self, path):
        assert path == promotion_flex.MEMORY_PROMOTION_FLEX_CONTROL_PATH
        outer = self

        class _Ref:
            def get(self):
                outer.reads += 1
                return _Snapshot(outer.payload)

        return _Ref()


class _Response:
    content = "result"


class _Model:
    def __init__(self, calls):
        self.calls = calls

    def bind(self, **kwargs):
        self.calls.append(("bind", kwargs))
        return self

    def invoke(self, prompt):
        self.calls.append(("invoke", prompt))
        return _Response()


def _flex_payload(**overrides):
    return {
        "mode": "flex",
        "generation": 1,
        "sample_percent": 100,
        "max_calls_per_run": 1,
        **overrides,
    }


def test_static_capability_defaults_off_without_firestore_read(monkeypatch):
    monkeypatch.delenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, raising=False)
    db = _Db(_flex_payload())

    assert promotion_flex.read_promotion_flex_control(db_client=db) == promotion_flex.PromotionFlexControl()
    assert db.reads == 0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        _flex_payload(mode="turbo"),
        _flex_payload(sample_percent=101),
        _flex_payload(max_calls_per_run=3),
        {**_flex_payload(), "unexpected": True},
    ],
)
def test_missing_or_invalid_live_control_fails_to_standard(monkeypatch, payload):
    monkeypatch.setenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "true")

    assert promotion_flex.read_promotion_flex_control(db_client=_Db(payload)) == promotion_flex.PromotionFlexControl()


def test_router_requests_flex_and_fences_the_result(monkeypatch):
    monkeypatch.setenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "true")
    db = _Db(_flex_payload())
    calls = []
    router = promotion_flex.PromotionFlexRunRouter(
        db_client=db,
        llm_factory=lambda *args, **kwargs: (calls.append(("factory", args, kwargs)) or _Model(calls)),
    )

    invoke = router.llm_invoke_for_uid("uid-a")
    assert invoke is not None
    assert invoke("prompt") == "result"
    assert calls == [
        (
            "factory",
            ("memory_conflict_flex",),
            {"request_timeout": promotion_flex.MEMORY_PROMOTION_FLEX_TIMEOUT_SECONDS},
        ),
        ("bind", {"service_tier": "flex"}),
        ("invoke", "prompt"),
    ]
    assert db.reads == 3  # initial control, before request, after response


def test_router_discards_result_when_live_generation_changes(monkeypatch):
    monkeypatch.setenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "true")
    db = _Db(_flex_payload())

    class _ChangingModel(_Model):
        def invoke(self, prompt):
            db.payload = _flex_payload(generation=2)
            return super().invoke(prompt)

    router = promotion_flex.PromotionFlexRunRouter(
        db_client=db,
        llm_factory=lambda *_args, **_kwargs: _ChangingModel([]),
    )
    invoke = router.llm_invoke_for_uid("uid-a")
    assert invoke is not None

    with pytest.raises(promotion_flex.PromotionFlexControlChanged):
        invoke("prompt")


def test_router_uses_standard_after_the_per_run_flex_cap(monkeypatch):
    monkeypatch.setenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "true")
    control = promotion_flex.PromotionFlexControl(mode="flex", generation=1, sample_percent=100, max_calls_per_run=1)
    calls = []
    router = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
        llm_factory=lambda *args, **kwargs: (calls.append(("factory", args, kwargs)) or _Model(calls)),
    )
    invoke = router.llm_invoke_for_uid("uid-a")
    assert invoke is not None

    assert invoke("first") == "result"
    assert invoke("second") == "result"
    assert calls[-2:] == [("factory", ("memory_conflict",), {}), ("invoke", "second")]
    assert router.llm_invoke_for_uid("uid-b") is None


def test_router_only_defers_transient_flex_errors(monkeypatch):
    monkeypatch.setenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "true")
    control = promotion_flex.PromotionFlexControl(mode="flex", generation=1, sample_percent=100, max_calls_per_run=1)

    class _FailingModel(_Model):
        def __init__(self, exc):
            super().__init__([])
            self.exc = exc

        def invoke(self, _prompt):
            raise self.exc

    class _CapacityError(Exception):
        status_code = 429

    transient = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
        llm_factory=lambda *_args, **_kwargs: _FailingModel(_CapacityError()),
    )
    transient_invoke = transient.llm_invoke_for_uid("uid-a")
    assert transient_invoke is not None
    with pytest.raises(promotion_flex.PromotionFlexDeferred):
        transient_invoke("prompt")

    permanent = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
        llm_factory=lambda *_args, **_kwargs: _FailingModel(ValueError("bad request")),
    )
    permanent_invoke = permanent.llm_invoke_for_uid("uid-a")
    assert permanent_invoke is not None
    with pytest.raises(ValueError, match="bad request"):
        permanent_invoke("prompt")


def test_router_uses_standard_when_a_flex_call_cannot_fit_the_job_budget(monkeypatch):
    monkeypatch.setenv(promotion_flex.MEMORY_PROMOTION_FLEX_CAPABLE_ENV, "true")
    control = promotion_flex.PromotionFlexControl(mode="flex", generation=1, sample_percent=100, max_calls_per_run=1)
    clock = iter([0.0, 2_401.0])
    calls = []
    router = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
        llm_factory=lambda *args, **kwargs: (calls.append(("factory", args, kwargs)) or _Model(calls)),
        monotonic=lambda: next(clock),
    )
    invoke = router.llm_invoke_for_uid("uid-a")
    assert invoke is not None

    assert invoke("late") == "result"
    assert calls == [("factory", ("memory_conflict",), {}), ("invoke", "late")]


def test_router_does_not_select_unsampled_uid():
    control = promotion_flex.PromotionFlexControl(mode="flex", generation=1, sample_percent=0, max_calls_per_run=1)
    router = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
    )

    assert router.llm_invoke_for_uid("uid-a") is None
