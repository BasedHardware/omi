from utils.memory.platform import build_memory_platform_capability
from utils.mcp_memory_platform import build_mcp_memory_platform_payload


def test_memory_platform_payload_identifies_backend_authority():
    payload = build_mcp_memory_platform_payload()

    assert payload['authority'] == 'omi_backend'
    assert payload['canonical_store'] == {
        'kind': 'firestore',
        'collection': 'memory_items',
        'apply_control': 'memory_state/apply_control',
    }


def test_memory_platform_payload_identifies_zkr_as_non_authoritative_mirror():
    replica = build_mcp_memory_platform_payload()['zkr']

    assert replica == {
        'export_format': 1,
        'replica_role': 'mirror',
        'write_mode': 'backend_ingest',
        'sync_implemented': False,
    }


def test_mcp_adapter_matches_the_api_payload_and_declares_both_surfaces():
    api_payload = build_memory_platform_capability().model_dump(mode='json')
    mcp_payload = build_mcp_memory_platform_payload()

    assert mcp_payload == api_payload
    assert mcp_payload['surfaces'] == {
        'rest': 'GET /v1/memory/platform',
        'mcp': 'memory_platform',
    }


def test_memory_platform_payload_returns_independent_values():
    first = build_mcp_memory_platform_payload()
    second = build_mcp_memory_platform_payload()

    first['zkr']['replica_role'] = 'changed'

    assert second['zkr']['replica_role'] == 'mirror'
