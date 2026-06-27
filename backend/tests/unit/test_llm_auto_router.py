from datetime import datetime, timezone

from utils.llm.auto_router import (
    AUTO_ROUTER_TTL_SECONDS,
    build_auto_route_table,
    parse_artificial_analysis_models,
)


def _payload():
    return {
        "data": [
            {
                "slug": "openai-gpt-5.4",
                "name": "GPT-5.4",
                "evaluations": {"artificial_analysis_intelligence_index": 94},
                "median_output_tokens_per_second": 80,
                "pricing": {"input": 8.0, "output": 24.0},
            },
            {
                "slug": "openai-gpt-5.4-mini",
                "name": "GPT-5.4 mini",
                "evaluations": {"artificial_analysis_intelligence_index": 83},
                "median_output_tokens_per_second": 180,
                "pricing": {"input": 1.2, "output": 4.8},
            },
            {
                "slug": "openai-gpt-4.1-mini",
                "name": "GPT-4.1 mini",
                "evaluations": {"artificial_analysis_intelligence_index": 75},
                "median_output_tokens_per_second": 90,
                "pricing": {"input": 3.0, "output": 12.0},
            },
            {
                "slug": "google-gemini-2.5-flash-lite",
                "name": "Gemini 2.5 Flash Lite",
                "evaluations": {"artificial_analysis_intelligence_index": 74},
                "median_output_tokens_per_second": 240,
                "pricing": {"input": 0.10, "output": 0.40},
            },
            {
                "slug": "openrouter-gemini-3-flash-preview",
                "name": "Gemini 3 Flash Preview",
                "evaluations": {"artificial_analysis_intelligence_index": 95},
                "median_output_tokens_per_second": 250,
                "pricing": {"input": 0.05, "output": 0.15},
            },
            {
                "slug": "anthropic-claude-sonnet-4-6",
                "name": "Claude Sonnet 4.6",
                "evaluations": {"artificial_analysis_intelligence_index": 91},
                "median_output_tokens_per_second": 85,
                "pricing": {"input": 3.0, "output": 15.0},
            },
        ]
    }


def test_parser_maps_specific_model_aliases_without_colliding():
    metrics = parse_artificial_analysis_models(_payload())

    assert "openai:gpt-5.4" in metrics
    assert "openai:gpt-5.4-mini" in metrics
    assert metrics["openai:gpt-5.4"].quality == 94
    assert metrics["openai:gpt-5.4-mini"].quality == 83


def test_parser_uses_provider_identity_before_alias_matching():
    payload = {
        "data": [
            {
                "slug": "openrouter-gpt-4.1-mini",
                "provider": "OpenRouter",
                "name": "GPT-4.1 Mini",
                "evaluations": {"artificial_analysis_intelligence_index": 99},
                "median_output_tokens_per_second": 250,
                "pricing": {"input": 0.01, "output": 0.02},
            }
        ]
    }

    metrics = parse_artificial_analysis_models(payload)

    assert "openai:gpt-4.1-mini" not in metrics


def test_parser_does_not_treat_model_family_inside_slug_as_provider():
    payload = {
        "data": [
            {
                "slug": "openrouter-claude-sonnet-4-6",
                "name": "Claude Sonnet 4.6",
                "evaluations": {"artificial_analysis_intelligence_index": 99},
                "median_output_tokens_per_second": 250,
                "pricing": {"input": 0.01, "output": 0.02},
            },
            {
                "slug": "openrouter-google-gemini-2.5-flash-lite",
                "name": "Gemini 2.5 Flash Lite",
                "evaluations": {"artificial_analysis_intelligence_index": 99},
                "median_output_tokens_per_second": 250,
                "pricing": {"input": 0.01, "output": 0.02},
            },
        ]
    }

    metrics = parse_artificial_analysis_models(payload)

    assert "anthropic:claude-sonnet-4-6" not in metrics
    assert "gemini:gemini-2.5-flash-lite" not in metrics


def test_build_route_table_picks_better_value_for_regular_features():
    route_table = build_auto_route_table(
        profile_name="premium",
        static_profile={"memories": ("gpt-4.1-mini", "openai")},
        benchmark_payload=_payload(),
        structured_output_features=set(),
        anthropic_only_features=set(),
        perplexity_only_features=set(),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    route = route_table["routes"]["memories"]
    assert route["source"] == "auto-router"
    assert route["model"] == "gemini-2.5-flash-lite"
    assert route["fallback_model"] == "gpt-4.1-mini"
    assert route_table["summary"]["dynamic_count"] == 1


def test_structured_features_do_not_route_to_openrouter():
    route_table = build_auto_route_table(
        profile_name="premium",
        static_profile={"trends": ("gemini-2.5-flash-lite", "gemini")},
        benchmark_payload=_payload(),
        structured_output_features={"trends"},
        anthropic_only_features=set(),
        perplexity_only_features=set(),
    )

    assert route_table["routes"]["trends"]["provider"] in {"openai", "gemini"}
    assert route_table["routes"]["trends"]["provider"] != "openrouter"


def test_anthropic_only_features_stay_in_anthropic_contract():
    route_table = build_auto_route_table(
        profile_name="premium",
        static_profile={"chat_agent": ("claude-sonnet-4-6", "anthropic")},
        benchmark_payload=_payload(),
        structured_output_features=set(),
        anthropic_only_features={"chat_agent"},
        perplexity_only_features=set(),
    )

    assert route_table["routes"]["chat_agent"]["provider"] == "anthropic"


def test_disabled_router_returns_static_routes_with_reason():
    route_table = build_auto_route_table(
        profile_name="premium",
        static_profile={"memories": ("gpt-4.1-mini", "openai")},
        benchmark_payload=None,
        structured_output_features=set(),
        anthropic_only_features=set(),
        perplexity_only_features=set(),
        pinned_features={"fair_use": ("gpt-5.1", "openai")},
        disabled_reason="benchmark_fetch_failed:RuntimeError",
    )

    assert route_table["routes"]["memories"]["source"] == "static"
    assert route_table["routes"]["memories"]["reason"] == "benchmark_fetch_failed:RuntimeError"
    assert route_table["routes"]["fair_use"]["source"] == "pinned"
    assert route_table["ttl_seconds"] == AUTO_ROUTER_TTL_SECONDS


def test_summary_counts_are_derived_after_pinned_overwrites():
    route_table = build_auto_route_table(
        profile_name="premium",
        static_profile={"fair_use": ("gemini-2.5-flash-lite", "gemini")},
        benchmark_payload=_payload(),
        structured_output_features=set(),
        anthropic_only_features=set(),
        perplexity_only_features=set(),
        pinned_features={"fair_use": ("gpt-5.1", "openai")},
    )

    assert route_table["routes"]["fair_use"]["source"] == "pinned"
    assert route_table["summary"]["dynamic_count"] == 0
    assert route_table["summary"]["static_count"] == 1
