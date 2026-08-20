from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (BACKEND_DIR / path).read_text(encoding='utf-8')


def test_v3_memories_route_uses_canonical_response_builders_for_public_egress():
    source = _read('routers/memories.py')

    assert 'from utils.memory.memory_api_response import memory_item_response, memory_list_response' in source
    assert 'jsonable_encoder(' not in source
    assert 'return memory_item_response(memory, MemoryApiExposure.CANONICAL)' in source
    assert 'memory_list_response(\n        memories,\n        MemoryApiExposure.CANONICAL' in source
    assert 'MemoryApiExposure.LEGACY' not in source


def test_external_memory_surfaces_use_exposure_aware_projection_before_returning_memory_objects():
    mcp_sse_source = _read('routers/mcp_sse.py')
    memory_service_source = _read('utils/memory/memory_service.py')

    create_tool = mcp_sse_source[
        mcp_sse_source.index('elif tool_name == "create_memory":') : mcp_sse_source.index(
            'elif tool_name == "delete_memory":'
        )
    ]
    assert (
        'return {"success": True, "memory": memory_api_payload(memory_db, MemoryApiExposure.CANONICAL)}' in create_tool
    )
    assert 'MemoryApiExposure.LEGACY' not in create_tool
    # Historical payload projection is permitted only inside the read-only
    # compatibility adapter; external writes must enter canonical authority.
    external_writes = memory_service_source[memory_service_source.index('def create_external_memory(') :]
    assert 'memory_write_payload(' not in external_writes
    assert '_canonical_write(' in external_writes
    assert 'self._canonical.write_batch(' in external_writes
