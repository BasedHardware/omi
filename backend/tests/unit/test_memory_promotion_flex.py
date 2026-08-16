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
        assert path == promotion_flex.BACKGROUND_FLEX_CONTROL_PATH
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
    return {"enabled": True, "generation": 1, **overrides}


def test_static_capability_defaults_off_without_firestore_read(monkeypatch):
    monkeypatch.delenv(promotion_flex.BACKGROUND_FLEX_CAPABLE_ENV, raising=False)
    db = _Db(_flex_payload())

    assert promotion_flex.read_promotion_flex_control(db_client=db) == promotion_flex.PromotionFlexControl()
    assert db.reads == 0


def test_gateway_flex_client_has_no_sdk_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(
        promotion_flex,
        "get_or_create_omi_gateway_llm",
        lambda *args, **kwargs: calls.append((args, kwargs)) or object(),
    )

    promotion_flex._get_gateway_flex_llm("memory_l2_flex", request_timeout=900.0)

    assert calls == [
        (
            ("omi:auto:memory-l2-flex",),
            {
                "options": {"request_timeout": 900.0, "max_retries": 0},
                "feature": "memory_l2_flex",
            },
        )
    ]


@pytest.mark.parametrize(
    "payload",
    [None, {}, _flex_payload(enabled="yes"), _flex_payload(generation=0), {**_flex_payload(), "unexpected": True}],
)
def test_missing_or_invalid_live_control_fails_to_standard(monkeypatch, payload):
    monkeypatch.setenv(promotion_flex.BACKGROUND_FLEX_CAPABLE_ENV, "true")

    assert promotion_flex.read_promotion_flex_control(db_client=_Db(payload)) == promotion_flex.PromotionFlexControl()


@pytest.mark.parametrize(
    ("standard_feature", "flex_feature", "workload"),
    [
        ("memory_conflict", "memory_conflict_flex", "memory_promotion"),
        ("memory_l2", "memory_l2_flex", "memory_l2"),
        ("memories", "x_memory_extraction_flex", "x_memory_extraction"),
    ],
)
def test_one_enabled_control_routes_every_scheduled_workload_to_flex(
    monkeypatch, standard_feature, flex_feature, workload
):
    monkeypatch.setenv(promotion_flex.BACKGROUND_FLEX_CAPABLE_ENV, "true")
    db = _Db(_flex_payload())
    calls = []
    router = promotion_flex.PromotionFlexRunRouter(
        db_client=db,
        flex_llm_factory=lambda *args, **kwargs: (calls.append(("factory", args, kwargs)) or _Model(calls)),
    )

    model = router.llm_for_uid("uid-a", standard_feature=standard_feature, flex_feature=flex_feature, workload=workload)
    assert model is not None
    assert model.invoke("prompt").content == "result"
    assert calls == [
        (
            "factory",
            (flex_feature,),
            {"request_timeout": promotion_flex.BACKGROUND_FLEX_TIMEOUT_SECONDS},
        ),
        ("bind", {"service_tier": "flex"}),
        ("invoke", "prompt"),
    ]


def test_disabled_control_selects_no_flex_model(monkeypatch):
    monkeypatch.setenv(promotion_flex.BACKGROUND_FLEX_CAPABLE_ENV, "true")
    router = promotion_flex.PromotionFlexRunRouter(db_client=_Db({"enabled": False, "generation": 1}))

    assert (
        router.llm_for_uid(
            "uid-a",
            standard_feature="memory_l2",
            flex_feature="memory_l2_flex",
            workload="memory_l2",
        )
        is None
    )
    assert router.llm_invoke_for_uid("uid-a") is None


def test_router_discards_result_when_live_generation_changes(monkeypatch):
    monkeypatch.setenv(promotion_flex.BACKGROUND_FLEX_CAPABLE_ENV, "true")
    db = _Db(_flex_payload())

    class _ChangingModel(_Model):
        def invoke(self, prompt):
            db.payload = _flex_payload(generation=2)
            return super().invoke(prompt)

    router = promotion_flex.PromotionFlexRunRouter(
        db_client=db,
        flex_llm_factory=lambda *_args, **_kwargs: _ChangingModel([]),
    )
    invoke = router.llm_invoke_for_uid("uid-a")
    assert invoke is not None

    with pytest.raises(promotion_flex.PromotionFlexControlChanged):
        invoke("prompt")


def test_router_only_defers_transient_flex_errors():
    control = promotion_flex.PromotionFlexControl(enabled=True, generation=1)

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
        flex_llm_factory=lambda *_args, **_kwargs: _FailingModel(_CapacityError()),
    )
    transient_invoke = transient.llm_invoke_for_uid("uid-a")
    assert transient_invoke is not None
    with pytest.raises(promotion_flex.PromotionFlexDeferred):
        transient_invoke("prompt")

    permanent = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
        flex_llm_factory=lambda *_args, **_kwargs: _FailingModel(ValueError("bad request")),
    )
    permanent_invoke = permanent.llm_invoke_for_uid("uid-a")
    assert permanent_invoke is not None
    with pytest.raises(ValueError, match="bad request"):
        permanent_invoke("prompt")


def test_router_defers_instead_of_using_standard_when_flex_cannot_fit_job_budget():
    control = promotion_flex.PromotionFlexControl(enabled=True, generation=1)
    clock = iter([0.0, 2_401.0])
    calls = []
    router = promotion_flex.PromotionFlexRunRouter(
        db_client=object(),
        control_reader=lambda **_kwargs: control,
        flex_llm_factory=lambda *args, **kwargs: (calls.append(("factory", args, kwargs)) or _Model(calls)),
        monotonic=lambda: next(clock),
    )
    model = router.llm_for_uid(
        "uid-a",
        standard_feature="memory_l2",
        flex_feature="memory_l2_flex",
        workload="memory_l2",
    )
    assert model is not None

    with pytest.raises(promotion_flex.PromotionFlexDeferred, match="job_budget"):
        model.invoke("late")
    assert calls == []
