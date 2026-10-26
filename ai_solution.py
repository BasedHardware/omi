```python
def save_user_preference_tool(
    tool_input: dict,
    memory: Memory,
    config: dict,
    user_id: str,
) -> dict:
    """Save user preference as a tool."""
    try:
        # Validate preference is a non-empty string
        if not isinstance(tool_input.get("preference"), str) or len(tool_input["preference"].strip()) == 0:
            raise ValueError("Error: Preference must be a non-empty string")

        # Ensure user_stated is correctly coerced to bool
        user_stated = is_true(tool_input.get("user_stated", ""))
        if isinstance(user_stated, str):
            if user_stated.lower() in (False, "false", "0", "no"):
                user_stated = False
            else:
                user_stated = True

        # Normalize replace_memory_id
        replace_memory_id = str(tool_input.get("replace_memory_id", "")).strip()

        # Get user ID
        uid = _get_uid(config)
        if uid:
            user_id = uid

        # Store the preference
        memory.update(
            key=f"preference:{user_id}",
            value=tool_input["preference"],
            replace_memory_id=replace_memory_id,
            user_stated=user_stated,
            **tool_input,
        )
    except Exception as e:
        return {"error": str(e)}

    return {"message": "Preference saved."}

def _get_uid(config: dict) -> str:
    """Get user ID from config, checking nested and top-level."""
    try:
        # Search nested configurable for user_id
        user_id = configurable.get("user_id")
        if user_id:
            return user_id
        # Search top-level configurable for user_id
        user_id = configurable.get(user_id_key)
        if user_id:
            return user_id
        # Search nested configurable for uid
        uid = configurable.get("uid")
        if uid:
            return uid
        # Search top-level configurable for uid
        uid = configurable.get("uid")
        if uid:
            return uid
        # Fall back to _agent_config
        return _agent_config.get("user_id")
    except AttributeError:
        return None

def preference_duplicate_message(hits: list) -> str:
    """Return message if duplicate."""
    if len(hits) > 0:
        if all(isinstance(hit, dict) for hit in hits):
            return f"Preference already set: {hits[0]['value']}."
    return "Preference saved."

def _write_provenance(preference: str, user_id: str) -> None:
    """Write provenance."""
    if preference:
        _agent_config["preference"] = preference
        _agent_config["user_id"] = user_id
```