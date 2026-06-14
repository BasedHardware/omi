from utils.memory_ingestion.models import SourceDescriptor
from utils.memory_ingestion.source_routing import SOURCE_ROUTER_VERSION, route_source


def test_source_router_passthrough_preserves_declared_source_type_with_benchmark_metadata():
    source = SourceDescriptor(
        source_type="benchmark_fixture",
        source_id="raw_voice_example",
        metadata={
            "benchmark_source_type": "voice_transcript",
            "benchmark_original_source_type": "voice_transcript",
        },
    )

    decision = route_source(source)

    assert decision.route_version == SOURCE_ROUTER_VERSION
    assert decision.declared_source_type == "benchmark_fixture"
    assert decision.effective_source_type == "benchmark_fixture"
    assert decision.reason == "declared_source_type_passthrough"
    assert decision.metadata["benchmark_source_type"] == "voice_transcript"
    assert decision.metadata["route_family"] == "current"


def test_source_router_chat_v7a_preserves_effective_source_type():
    source = SourceDescriptor(source_type="chat_exchange", source_id="raw_chat_example", metadata={})

    decision = route_source(source, route_family="v7a")

    assert decision.declared_source_type == "chat_exchange"
    assert decision.effective_source_type == "chat_exchange"
    assert decision.metadata["route_family"] == "v7a"


def test_source_router_records_native_source_type():
    source = SourceDescriptor(source_type="voice_transcript", source_id="raw_voice_example", metadata={})

    decision = route_source(source)

    assert decision.declared_source_type == "voice_transcript"
    assert decision.effective_source_type == "voice_transcript"
    assert decision.model_dump()["route_version"] == SOURCE_ROUTER_VERSION


def test_source_router_liberal_l1_records_candidate_contract():
    source = SourceDescriptor(source_type="voice_transcript", source_id="raw_voice_example", metadata={})

    decision = route_source(source, route_family="liberal_l1_v1")

    assert decision.declared_source_type == "voice_transcript"
    assert decision.effective_source_type == "voice_transcript"
    assert decision.reason == "liberal_l1_v1_selected"
    assert decision.metadata["route_family"] == "liberal_l1_v1"
    assert decision.metadata["l1_contract"] == "liberal_memory_candidate.v1"
    assert decision.metadata["l2_required_for_storage"] is True
