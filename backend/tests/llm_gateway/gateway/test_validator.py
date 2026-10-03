import pytest
from llm_gateway.gateway.validator import (
    validate_chat_completion_request,
    validate_embedding_request,
    validate_systemone_request,
    _validate_systemone_question,
    _validate_messages,
    _validate_text_content,
    _is_supported_content_part,
    _is_file_content_part,
    _is_text_content_part,
    _is_image_url_content_part,
    _validate_response_format,
    _validate_forwarded_params,
    _validate_reasoning_effort,
    _validate_service_tier,
    _validate_prompt_cache_options,
    _validate_output_limit_aliases,
    _is_string_map,
)
from llm_gateway.gateway.schemas import (
    LaneConfig,
    Capabilities,
    StructuredOutputMode,
    Surface,
    Objective,
    CredentialPolicy,
    CredentialMode,
)
from llm_gateway.gateway.errors import GatewayInvalidRequestError, GatewayCapabilityMismatchError


def test_validate_chat_completion_request():
    lane = LaneConfig(
        lane_id="omi:auto:memory-conflict-flex",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            streaming=True,
            tools=True,
            structured_output=StructuredOutputMode.JSON_SCHEMA,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )

    # Missing model
    with pytest.raises(GatewayInvalidRequestError):
        validate_chat_completion_request({"messages": [{"role": "user", "content": "hello"}]}, lane)

    # Valid
    request = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    }
    validated = validate_chat_completion_request(request, lane)
    assert validated.model == "gpt-4o"
    assert len(validated.messages) == 1


def test_validate_messages():
    # Empty messages
    with pytest.raises(GatewayInvalidRequestError):
        _validate_messages([])

    # Invalid message type
    with pytest.raises(GatewayInvalidRequestError):
        _validate_messages(["not a dict"])

    # Missing role
    with pytest.raises(GatewayInvalidRequestError):
        _validate_messages([{"content": "hello"}])

    # Assistant missing content is padded
    validated = _validate_messages([{"role": "assistant"}])
    assert validated[0]["content"] == ""

    # User missing content
    with pytest.raises(GatewayInvalidRequestError):
        _validate_messages([{"role": "user"}])

    # Valid text message
    validated = _validate_messages([{"role": "user", "content": "hello"}])
    assert len(validated) == 1


def test_validate_text_content():
    # Valid string
    _validate_text_content("hello", param="content")

    # Invalid type
    with pytest.raises(GatewayCapabilityMismatchError):
        _validate_text_content({"not": "supported"}, param="content")


def test_is_text_content_part():
    assert _is_text_content_part({"type": "text", "text": "hello"})
    assert not _is_text_content_part({"type": "image_url"})

    with pytest.raises(GatewayInvalidRequestError):
        _is_text_content_part({"type": "text", "text": "hello", "prompt_cache_breakpoint": {"mode": "invalid"}})


def test_validate_response_format():
    lane_json_schema = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.JSON_SCHEMA,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )

    # Valid json schema
    fmt = _validate_response_format(
        {"type": "json_schema", "json_schema": {"name": "TestSchema", "schema": {"type": "object"}}}, lane_json_schema
    )
    assert fmt is not None
    assert fmt["type"] == "json_schema"


def test_validate_forwarded_params():
    lane = LaneConfig(
        lane_id="omi:auto:memory-conflict-flex",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    request = {"max_tokens": 100, "service_tier": "flex", "reasoning_effort": "high"}
    forwarded = _validate_forwarded_params(request, lane)
    assert forwarded["max_tokens"] == 100
    assert forwarded["service_tier"] == "flex"
    assert forwarded["reasoning_effort"] == "high"


def test_validate_reasoning_effort():
    _validate_reasoning_effort("high")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_reasoning_effort("invalid")


def test_validate_service_tier():
    lane = LaneConfig(
        lane_id="omi:auto:memory-conflict-flex",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    _validate_service_tier("flex", lane)

    lane_invalid = LaneConfig(
        lane_id="omi:auto:invalid-lane",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    with pytest.raises(GatewayCapabilityMismatchError):
        _validate_service_tier("flex", lane_invalid)


def test_validate_prompt_cache_options():
    _validate_prompt_cache_options({"mode": "explicit", "ttl": "30m"})
    with pytest.raises(GatewayInvalidRequestError):
        _validate_prompt_cache_options({"mode": "invalid"})


def test_validate_output_limit_aliases():
    _validate_output_limit_aliases({"max_tokens": 10})
    _validate_output_limit_aliases({"max_completion_tokens": 10})

    with pytest.raises(GatewayInvalidRequestError):
        _validate_output_limit_aliases({"max_tokens": -1})

    with pytest.raises(GatewayInvalidRequestError):
        _validate_output_limit_aliases({"max_tokens": 10, "max_completion_tokens": 20})


def test_validate_chat_completion_request_more_errors():
    lane = LaneConfig(
        lane_id="omi:auto:memory-conflict-flex",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            streaming=False,
            tools=False,
            structured_output=StructuredOutputMode.JSON_SCHEMA,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )

    # Streaming not supported
    with pytest.raises(GatewayCapabilityMismatchError):
        validate_chat_completion_request(
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}], "stream": True}, lane
        )

    # Tools not supported
    with pytest.raises(GatewayCapabilityMismatchError):
        validate_chat_completion_request(
            {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hello"}],
                "tools": [{"type": "function", "function": {"name": "test"}}],
            },
            lane,
        )


def test_is_string_map():
    assert _is_string_map({"a": "b"})
    assert not _is_string_map("not a dict")
    assert not _is_string_map({"a": 1})
    assert not _is_string_map({"a": "b"}, allowed_keys=frozenset({"c"}))


def test_is_file_content_part():
    assert _is_file_content_part({"type": "file", "file": {"file_id": "test"}})
    assert not _is_file_content_part({"type": "text"})
    assert not _is_file_content_part("not a dict")
    assert not _is_file_content_part({"type": "file", "file": "not a dict"})
    assert not _is_file_content_part({"type": "file", "file": {"file_id": 1}})


def test_is_image_url_content_part():
    assert _is_image_url_content_part({"type": "image_url", "image_url": {"url": "http://test"}})
    assert not _is_image_url_content_part({"type": "text"})
    assert not _is_image_url_content_part("not a dict")
    assert not _is_image_url_content_part({"type": "image_url", "image_url": "not a dict"})
    assert not _is_image_url_content_part({"type": "image_url", "image_url": {"url": 1}})


def test_validate_response_format_more_errors():
    lane_none = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )

    lane_json_schema = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.JSON_SCHEMA,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )

    assert _validate_response_format(None, lane_none) is None

    with pytest.raises(GatewayInvalidRequestError):
        _validate_response_format("not a dict", lane_none)

    with pytest.raises(GatewayCapabilityMismatchError):
        _validate_response_format({"type": "json_object"}, lane_none)

    with pytest.raises(GatewayCapabilityMismatchError):
        _validate_response_format({"type": "json_schema"}, lane_none)

    with pytest.raises(GatewayCapabilityMismatchError):
        _validate_response_format({"type": "invalid"}, lane_json_schema)

    with pytest.raises(GatewayInvalidRequestError):
        _validate_response_format({"type": "json_schema", "json_schema": "not a dict"}, lane_json_schema)

    with pytest.raises(GatewayInvalidRequestError):
        _validate_response_format({"type": "json_schema", "json_schema": {"name": ""}}, lane_json_schema)

    with pytest.raises(GatewayInvalidRequestError):
        _validate_response_format(
            {"type": "json_schema", "json_schema": {"name": "test", "schema": "not a dict"}}, lane_json_schema
        )


def test_validate_forwarded_params_unsupported():
    lane = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    with pytest.raises(GatewayInvalidRequestError):
        _validate_forwarded_params({"invalid_param": 1}, lane)


def test_is_supported_content_part():
    assert _is_supported_content_part({"type": "text", "text": "hello"})
    assert _is_supported_content_part({"type": "image_url", "image_url": {"url": "http://test"}})
    assert _is_supported_content_part({"type": "file", "file": {"file_id": "test"}})
    assert not _is_supported_content_part({"type": "invalid"})


def test_validate_text_content_list():
    _validate_text_content([{"type": "text", "text": "hello"}], param="content")
    with pytest.raises(GatewayCapabilityMismatchError):
        _validate_text_content([{"type": "invalid"}], param="content")


def test_validate_chat_completion_request_tool_choice():
    lane = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            streaming=False,
            tools=False,
            structured_output=StructuredOutputMode.JSON_SCHEMA,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    with pytest.raises(GatewayCapabilityMismatchError):
        validate_chat_completion_request(
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}], "tool_choice": "auto"}, lane
        )


def test_validate_embedding_request():
    lane = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_EMBEDDINGS,
        capabilities=Capabilities(
            streaming=False,
            tools=False,
            structured_output=StructuredOutputMode.NONE,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"input": "test"}, lane)
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"model": "test", "input": 123}, lane)
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"model": "test", "input": ["", "test"]}, lane)
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"model": "test", "input": []}, lane)
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"model": "test", "input": "test", "invalid": 1}, lane)
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"model": "test", "input": "test", "task_type": "  "}, lane)
    with pytest.raises(GatewayInvalidRequestError):
        validate_embedding_request({"model": "test", "input": "test", "title": "  "}, lane)

    req = validate_embedding_request(
        {"model": "test", "input": "test", "task_type": "retrieval_query", "title": "my title"}, lane
    )
    assert req.model == "test"
    assert req.inputs == ("test",)
    assert req.task_type == "retrieval_query"
    assert req.title == "my title"

    req2 = validate_embedding_request({"model": "test", "input": ["test1", "test2"]}, lane)
    assert req2.inputs == ("test1", "test2")


def test_validate_systemone_request():
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request({"state": "test"})
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request(
            {
                "model": "test",
                "state": "test",
                "questions": {"a": {"type": "noul", "instructions": "test"}},
                "invalid": 1,
            }
        )
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request(
            {"model": "test", "state": "  ", "questions": {"a": {"type": "noul", "instructions": "test"}}}
        )
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request(
            {"model": "test", "state": "a" * 1000000, "questions": {"a": {"type": "noul", "instructions": "test"}}}
        )
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request({"model": "test", "state": "test"})
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request(
            {
                "model": "test",
                "state": "test",
                "questions": {f"q{i}": {"type": "noul", "instructions": "test"} for i in range(100)},
            }
        )
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request(
            {"model": "test", "state": "test", "questions": {"": {"type": "noul", "instructions": "test"}}}
        )
    with pytest.raises(GatewayInvalidRequestError):
        validate_systemone_request({"model": "test", "state": "test", "questions": {"q1": "invalid"}})

    req = validate_systemone_request(
        {"model": "test", "state": "test", "questions": {"q1": {"type": "noul", "instructions": "test"}}}
    )
    assert req.model == "test"
    assert req.state == "test"
    assert "q1" in req.questions


def test_validate_systemone_question():
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "noul", "instructions": "test", "invalid": 1}, param="test")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "invalid", "instructions": "test"}, param="test")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "noul", "instructions": "  "}, param="test")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question(
            {"type": "noul", "instructions": "test", "criteria": {"invalid": "test"}}, param="test"
        )
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "choice", "instructions": "test", "criteria": {"a": 1}}, param="test")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question(
            {"type": "choice", "instructions": "test", "criteria": {"a": "test"}}, param="test"
        )
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "score", "instructions": "test", "criteria": "invalid"}, param="test")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "score", "instructions": "test", "criteria": ["a"]}, param="test")
    with pytest.raises(GatewayInvalidRequestError):
        _validate_systemone_question({"type": "score", "instructions": "test", "criteria": ["a", "  "]}, param="test")

    q1 = _validate_systemone_question({"type": "noul", "instructions": "test"}, param="test")
    assert q1["type"] == "noul"

    q2 = _validate_systemone_question(
        {"type": "choice", "instructions": "test", "criteria": {"a": "A", "b": "B"}}, param="test"
    )
    assert q2["type"] == "choice"

    q3 = _validate_systemone_question({"type": "score", "instructions": "test", "criteria": ["a", "b"]}, param="test")
    assert q3["type"] == "score"


def test_is_string_map_coverage():
    assert not _is_string_map({"a": 1})
    assert not _is_string_map({" ": "b"})
    assert not _is_string_map({"a": " "})


def test_validate_response_format_json_object():
    lane = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.JSON_OBJECT,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    fmt = _validate_response_format({"type": "json_object"}, lane)
    assert fmt["type"] == "json_object"


def test_validate_forwarded_params_coverage():
    lane = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    _validate_forwarded_params({"prompt_cache_options": {"mode": "explicit", "ttl": "30m"}, "tools": []}, lane)


def test_validate_service_tier_invalid():
    lane = LaneConfig(
        lane_id="omi:auto:test",
        surface=Surface.OPENAI_CHAT_COMPLETIONS,
        capabilities=Capabilities(
            structured_output=StructuredOutputMode.NONE,
            streaming=False,
            tools=False,
            text_input=True,
            translation=False,
        ),
        objective=Objective(quality=0.5, latency=0.3, cost=0.2),
        credential_policy=CredentialPolicy(mode=CredentialMode.BYOK),
        active_route="r",
        last_known_good="r",
    )
    with pytest.raises(GatewayInvalidRequestError):
        _validate_service_tier("invalid", lane)


def test_validate_prompt_cache_options_invalid():
    with pytest.raises(GatewayInvalidRequestError):
        _validate_prompt_cache_options("invalid")


def test_is_text_content_part_invalid():
    assert not _is_text_content_part("not a dict")
