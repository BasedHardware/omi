import uuid

from fastapi import Request

from llm_gateway.gateway.request_context import request_id_for, resolve_request_id

# The JIT budget surface these tests once covered was removed in #22209.


def build_mock_request(headers_dict, state_request_id=None):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in headers_dict.items()],
        "state": {"request_id": state_request_id} if state_request_id is not None else {},
    }
    req = Request(scope)

    return req


def test_request_id_for():
    req = build_mock_request({}, "test-req-id")
    assert request_id_for(req) == "test-req-id"

    req_empty = build_mock_request({}, "")
    assert request_id_for(req_empty) == "unknown"

    req_none = build_mock_request({})
    assert request_id_for(req_none) == "unknown"


def test_resolve_request_id():
    valid_uuid = str(uuid.uuid4())
    # Should keep valid UUID
    assert resolve_request_id(valid_uuid) == valid_uuid

    # Should fix case of UUID
    assert resolve_request_id(valid_uuid.upper()) == valid_uuid

    # Invalid UUID generates new one
    invalid_res = resolve_request_id("not-a-uuid")
    assert invalid_res != "not-a-uuid"
    assert uuid.UUID(invalid_res)  # Should not raise

    # None generates new one
    none_res = resolve_request_id(None)
    assert uuid.UUID(none_res)

    # Too long generates new one
    too_long = "a" * 100
    long_res = resolve_request_id(too_long)
    assert uuid.UUID(long_res)
