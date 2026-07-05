from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (BACKEND_DIR / path).read_text(encoding='utf-8')


def test_v3_memories_route_uses_memory_response_builders_for_public_egress():
    source = _read('routers/memories.py')

    assert (
        'from utils.memory.memory_api_response import memory_batch_response, memory_item_response, memory_list_response'
        in source
    )
    assert 'jsonable_encoder(' not in source
    assert (
        'exposure = MemoryApiExposure.CANONICAL if canonical_lifecycle_exposed else MemoryApiExposure.LEGACY' in source
    )
    assert 'memory_list_response(memory_response.body or [], exposure' in source
    assert 'memory_list_response(\n        memories,\n        MemoryApiExposure.LEGACY' in source
    assert 'memory_item_response(memory, MemoryApiExposure.LEGACY)' in source
    assert 'memory_batch_response(memories, MemoryApiExposure.LEGACY' in source


def test_external_memory_surfaces_use_exposure_aware_projection_before_returning_memory_objects():
    mcp_sse_source = _read('routers/mcp_sse.py')
    memory_service_source = _read('utils/memory/memory_service.py')

    create_tool = mcp_sse_source[
        mcp_sse_source.index('elif tool_name == "create_memory":') : mcp_sse_source.index(
            'elif tool_name == "delete_memory":'
        )
    ]
    assert 'exposure = (' in create_tool
    assert 'MemoryApiExposure.CANONICAL' in create_tool
    assert 'MemoryApiExposure.LEGACY' in create_tool
    assert 'return {"success": True, "memory": memory_api_payload(memory_db, exposure)}' in create_tool
    assert 'memory_write_payload(memory_db, MemoryApiExposure.LEGACY)' in memory_service_source
    assert '[memory_write_payload(memory, MemoryApiExposure.LEGACY) for memory in memory_dbs]' in memory_service_source
