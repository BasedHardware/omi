import pytest
from pydantic import ValidationError

from llm_gateway.gateway.schemas import (
    BenchmarkSource,
    Capabilities,
    CredentialMode,
    CredentialPolicy,
    Evidence,
    FailureClass,
    FallbackPolicy,
    FeatureBundle,
    GeneratedRouteOverride,
    LaneConfig,
    Objective,
    OutputBudgetPolicy,
    ProviderRef,
    RetryPolicy,
    RolloutPolicy,
    RolloutStage,
    RouteArtifact,
    StructuredOutputMode,
    Surface,
    TimeoutPolicy,
    compute_route_artifact_digest,
)

def test_capabilities_translation_validation():
    # Valid
    cap = Capabilities(
        text_input=True,
        streaming=False,
        structured_output=StructuredOutputMode.JSON_SCHEMA,
        tools=False,
        translation=True,
    )
    assert cap.translation is True

    # Invalid: translation without json_schema
    with pytest.raises(ValidationError, match="translation lanes require json_schema structured output"):
        Capabilities(
            text_input=True,
            streaming=False,
            structured_output=StructuredOutputMode.JSON_OBJECT,
            tools=False,
            translation=True,
        )

def test_objective_weights_validation():
    # Valid sum to 1.0
    obj = Objective(quality=0.5, latency=0.3, cost=0.2)
    assert obj.quality == 0.5

    # Invalid: does not sum to 1.0
    with pytest.raises(ValidationError, match="objective weights must sum to 1.0"):
        Objective(quality=0.5, latency=0.5, cost=0.1)

def test_rollout_policy_validation():
    # Valid
    active = RolloutPolicy(stage=RolloutStage.ACTIVE, percent=100.0)
    assert active.percent == 100.0

    disabled = RolloutPolicy(stage=RolloutStage.DISABLED, percent=0.0)
    assert disabled.percent == 0.0

    # Invalid: active not 100%
    with pytest.raises(ValidationError, match="active rollout stage must use percent 100"):
        RolloutPolicy(stage=RolloutStage.ACTIVE, percent=50.0)

    # Invalid: disabled not 0%
    with pytest.raises(ValidationError, match="disabled rollout stage must use percent 0"):
        RolloutPolicy(stage=RolloutStage.DISABLED, percent=10.0)

def test_evidence_is_prod_eligible():
    # Prod eligible
    ev1 = Evidence(
        benchmark_snapshot="snap",
        eval_report="report",
        benchmark_source=BenchmarkSource.OMI_EVAL,
        dev_only=False
    )
    assert ev1.is_prod_eligible() is True

    # Not prod eligible due to dev_only
    ev2 = Evidence(
        benchmark_snapshot="snap",
        eval_report="report",
        benchmark_source=BenchmarkSource.OMI_EVAL,
        dev_only=True
    )
    assert ev2.is_prod_eligible() is False

    # Not prod eligible due to MOCK source
    ev3 = Evidence(
        benchmark_snapshot="snap",
        eval_report="report",
        benchmark_source=BenchmarkSource.MOCK,
        dev_only=False
    )
    assert ev3.is_prod_eligible() is False

def test_credential_policy_overlap():
    # Valid
    pol = CredentialPolicy(
        mode=CredentialMode.OMI_PAID,
        fallback_eligible_failure_classes=[FailureClass.PROVIDER_INVALID_REQUEST],
        never_fallback_failure_classes=[FailureClass.TIMEOUT_BEFORE_OUTPUT]
    )
    assert pol.mode == CredentialMode.OMI_PAID

    # Invalid: overlapping failure classes
    with pytest.raises(ValidationError, match="credential fallback class sets overlap: timeout_before_output"):
        CredentialPolicy(
            mode=CredentialMode.OMI_PAID,
            fallback_eligible_failure_classes=[FailureClass.TIMEOUT_BEFORE_OUTPUT],
            never_fallback_failure_classes=[FailureClass.TIMEOUT_BEFORE_OUTPUT]
        )

def test_fallback_policy_overlap():
    # Valid
    pol = FallbackPolicy(
        fallback_on=[FailureClass.PROVIDER_INVALID_REQUEST],
        never_fallback_on=[FailureClass.TIMEOUT_BEFORE_OUTPUT]
    )
    assert len(pol.fallback_on) == 1

    # Invalid: overlapping failure classes
    with pytest.raises(ValidationError, match="fallback_on and never_fallback_on overlap: timeout_before_output"):
        FallbackPolicy(
            fallback_on=[FailureClass.TIMEOUT_BEFORE_OUTPUT],
            never_fallback_on=[FailureClass.TIMEOUT_BEFORE_OUTPUT]
        )

def test_route_artifact_digest():
    artifact = RouteArtifact(
        route_artifact_id="id-1",
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        primary=ProviderRef(provider="openai", model="gpt-4"),
        timeouts=TimeoutPolicy(request_ms=1000),
        retry=RetryPolicy(max_attempts=3),
        capabilities=Capabilities(
            text_input=True,
            streaming=False,
            structured_output=StructuredOutputMode.NONE,
            tools=False
        ),
        evidence=Evidence(
            benchmark_snapshot="snap",
            eval_report="report",
            benchmark_source=BenchmarkSource.OMI_EVAL
        ),
        rollout=RolloutPolicy(stage=RolloutStage.ACTIVE, percent=100.0),
        credential_policy=CredentialPolicy(mode=CredentialMode.OMI_PAID),
        fallback_policy=FallbackPolicy()
    )

    digest = artifact.content_digest
    assert digest.startswith("sha256:")
    assert artifact.artifact_digest is None

    # Validation error for artifact_digest format
    with pytest.raises(ValidationError, match="artifact_digest must use sha256:<hex> format"):
        artifact.artifact_digest = "md5:123"
        RouteArtifact.model_validate(artifact.model_dump())

def test_compute_route_artifact_digest_dict():
    payload = {
        "route_artifact_id": "id-1",
        "lane_id": "omi:auto:test",
        "artifact_digest": "sha256:will_be_ignored",
        "content_digest": "will_be_ignored_too"
    }

    digest = compute_route_artifact_digest(payload)
    assert digest.startswith("sha256:")

def test_feature_bundle():
    bundle = FeatureBundle(
        feature="test-feature",
        lane_id="omi:auto:test",
        prompt_version="1.0",
        parser_version="1.0",
        eval_suite="suite-1",
        promotion_gates={"gate1": "value1"}
    )
    assert bundle.feature == "test-feature"
    assert bundle.lane_id == "omi:auto:test"

def test_lane_id_regex():
    with pytest.raises(ValidationError):
        FeatureBundle(
            feature="test",
            lane_id="invalid-lane-id",
            prompt_version="1",
            parser_version="1",
            eval_suite="1"
        )

    # Valid
    FeatureBundle(
        feature="test",
        lane_id="omi:auto:valid-id",
        prompt_version="1",
        parser_version="1",
        eval_suite="1"
    )

def test_route_artifact_digest_valid_value():
    artifact = RouteArtifact(
        route_artifact_id="id-1",
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        primary=ProviderRef(provider="openai", model="gpt-4"),
        timeouts=TimeoutPolicy(request_ms=1000),
        retry=RetryPolicy(max_attempts=3),
        capabilities=Capabilities(
            text_input=True,
            streaming=False,
            structured_output=StructuredOutputMode.NONE,
            tools=False
        ),
        evidence=Evidence(
            benchmark_snapshot="snap",
            eval_report="report",
            benchmark_source=BenchmarkSource.OMI_EVAL
        ),
        rollout=RolloutPolicy(stage=RolloutStage.ACTIVE, percent=100.0),
        credential_policy=CredentialPolicy(mode=CredentialMode.OMI_PAID),
        fallback_policy=FallbackPolicy(),
        artifact_digest="sha256:12345"
    )
    assert artifact.artifact_digest == "sha256:12345"

def test_lane_config():
    config = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            text_input=True,
            streaming=False,
            structured_output=StructuredOutputMode.NONE,
            tools=False
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.OMI_PAID),
        active_route="route-1",
        last_known_good="route-0"
    )
    assert config.lane_id == "omi:auto:test"
    assert config.active_route == "route-1"

def test_output_budget_policy():
    policy = OutputBudgetPolicy(
        experiment="test-experiment",
        max_completion_tokens=4000
    )
    assert policy.experiment == "test-experiment"
    assert policy.max_completion_tokens == 4000

    with pytest.raises(ValidationError):
        OutputBudgetPolicy(experiment="invalid experiment name!", max_completion_tokens=4000)

def test_generated_route_override():
    override = GeneratedRouteOverride(
        feature="test-feature",
        primary=ProviderRef(provider="openai", model="gpt-4"),
        provider_options={"test": "value"},
        request_timeout_ms=1000
    )
    assert override.feature == "test-feature"
    assert override.primary.provider == "openai"
    assert override.provider_options == {"test": "value"}
    assert override.request_timeout_ms == 1000
