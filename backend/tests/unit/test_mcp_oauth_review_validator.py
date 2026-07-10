from scripts.validate_mcp_oauth_review_config import validate_submission_config, validate_tool_metadata


def test_validator_accepts_structured_public_chatgpt_client():
    errors = validate_submission_config(
        {
            "server_url": "https://api.omi.me/v1/mcp/sse",
            "authentication": "oauth",
            "oauth_client": {
                "client_id": "omi-chatgpt-prod",
                "token_endpoint_auth_method": "none",
            },
        }
    )

    assert errors == []


def test_validator_rejects_null_oauth_client_for_oauth_flow():
    errors = validate_submission_config(
        {
            "server_url": "https://api.omi.me/v1/mcp/sse",
            "authentication": "oauth",
            "oauth_client": None,
        }
    )

    assert any("oauth_client[1] is null" in error for error in errors)


def test_validator_rejects_legacy_client_id_and_auth_method_mismatch():
    errors = validate_submission_config(
        {
            "oauth_client": {
                "client_id": "omi",
                "token_endpoint_auth_method": "client_secret_post",
            }
        }
    )

    assert any("client_id='omi' is rejected" in error for error in errors)


def test_validator_rejects_chatgpt_secret_post_mismatch_without_printing_secret_value():
    errors = validate_submission_config(
        {
            "oauth_client": {
                "client_id": "omi-chatgpt-prod",
                "token_endpoint_auth_method": "client_secret_post",
                "client_secret": "should-not-appear",
            }
        }
    )

    encoded = "\n".join(errors)
    assert "client_secret_post" in encoded
    assert "raw secret fields" in encoded
    assert "should-not-appear" not in encoded


def test_validator_detects_tool_metadata_drift():
    errors = validate_tool_metadata({"tools": [{"name": "search_memories"}]}, {"tools": [{"name": "create_memory"}]})

    assert any("missing live tools: create_memory" in error for error in errors)
    assert any("stale tools: search_memories" in error for error in errors)


def test_validator_reads_jsonrpc_tools_list_envelopes():
    errors = validate_tool_metadata(
        {"result": {"tools": [{"name": "search_memories"}]}},
        {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "search_memories"}]}},
    )

    assert errors == []
