from utils.api_key_families import (
    api_key_family,
    wrong_key_family_detail,
    FIREBASE_FAMILY,
    MCP_FAMILY,
    DEV_FAMILY,
    MCP_KEY_PREFIX,
    DEV_KEY_PREFIX,
)


def test_api_key_family_inference():
    assert api_key_family(f'{MCP_KEY_PREFIX}12345') == MCP_FAMILY
    assert api_key_family(f'{DEV_KEY_PREFIX}abcdef') == DEV_FAMILY
    assert api_key_family('custom_token_123') == FIREBASE_FAMILY
    assert api_key_family('') == FIREBASE_FAMILY
    assert api_key_family(None) == FIREBASE_FAMILY


def test_wrong_key_family_detail_matching_family_returns_none():
    mcp_token = f'{MCP_KEY_PREFIX}valid_token'
    assert wrong_key_family_detail(mcp_token, MCP_FAMILY) is None

    dev_token = f'{DEV_KEY_PREFIX}valid_token'
    assert wrong_key_family_detail(dev_token, DEV_FAMILY) is None


def test_wrong_key_family_detail_firebase_family_returns_none():
    assert wrong_key_family_detail('some_firebase_token', MCP_FAMILY) is None
    assert wrong_key_family_detail(None, DEV_FAMILY) is None
    assert wrong_key_family_detail('', MCP_FAMILY) is None


def test_wrong_key_family_detail_mismatch_returns_actionable_message():
    mcp_token = f'{MCP_KEY_PREFIX}secret'
    detail = wrong_key_family_detail(mcp_token, DEV_FAMILY)
    assert detail is not None
    assert 'MCP API keys (omi_mcp_...)' in detail
    assert 'Developer API key' in detail

    dev_token = f'{DEV_KEY_PREFIX}secret'
    detail2 = wrong_key_family_detail(dev_token, MCP_FAMILY)
    assert detail2 is not None
    assert 'Developer API keys (omi_dev_...)' in detail2
    assert 'MCP API key' in detail2


def test_wrong_key_family_detail_firebase_route_rejects_mcp_and_dev_keys():
    mcp_token = f'{MCP_KEY_PREFIX}secret'
    detail_mcp = wrong_key_family_detail(mcp_token, FIREBASE_FAMILY)
    assert detail_mcp is not None
    assert 'MCP API keys (omi_mcp_...)' in detail_mcp
    assert 'This endpoint requires a Firebase ID token from a signed-in Omi app' in detail_mcp

    dev_token = f'{DEV_KEY_PREFIX}secret'
    detail_dev = wrong_key_family_detail(dev_token, FIREBASE_FAMILY)
    assert detail_dev is not None
    assert 'Developer API keys (omi_dev_...)' in detail_dev
    assert 'This endpoint requires a Firebase ID token from a signed-in Omi app' in detail_dev
