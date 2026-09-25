# Assuming we only need to test the helper function
from routers.updates import _sanitize_update_error

def test_sanitize_update_error() -> None:
    # 1. Exact match leaks should be masked
    assert _sanitize_update_error(ValueError("generation mismatch: expected 1, current 2")) == "invalid_update_generation_state"
    assert _sanitize_update_error(ValueError("current release mismatch: expected X, current Y")) == "invalid_update_release_state"
    assert _sanitize_update_error(ValueError("release_id already exists with different immutable metadata")) == "invalid_update_immutable_conflict"
    
    # 2. General database format errors
    assert _sanitize_update_error(ValueError("release_sha must be 40 lowercase hex or null")) == "invalid_update_parameter"
    assert _sanitize_update_error(ValueError("invalid platform")) == "invalid_update_target"
    
    # 3. Completely unknown value errors should be generic
    assert _sanitize_update_error(ValueError("Some internal random db error")) == "invalid_update_state"
