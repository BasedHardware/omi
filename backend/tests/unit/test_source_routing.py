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


def test_source_router_records_native_source_type():
    source = SourceDescriptor(source_type="voice_transcript", source_id="raw_voice_example", metadata={})

    decision = route_source(source)

    assert decision.declared_source_type == "voice_transcript"
    assert decision.effective_source_type == "voice_transcript"
    assert decision.model_dump()["route_version"] == SOURCE_ROUTER_VERSION
