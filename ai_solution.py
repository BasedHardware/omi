```python
def _clean_id(uid: str) -> str:
    """Sanitize uid."""
    if not isinstance(uid, str):
        uid = str(uid)
    # Validate and sanitize uid
    if not uid:
        raise ValueError("uid must not be empty.")
    if len(uid) > 255:
        raise ValueError("uid must be <= 255 chars.")
    if ".." in uid:
        raise ValueError("uid cannot contain ..")
    if "/" in uid:
        raise ValueError("uid cannot contain /")
    if "\\" in uid:
        raise ValueError("uid cannot contain \\")
    if "\x00" in uid:
        raise ValueError("uid cannot contain null bytes.")
    return uid

def _clean_day(day: str) -> str:
    """Sanitize day."""
    if not isinstance(day, str):
        day = str(day)
    # Validate and sanitize day
    if not day:
        raise ValueError("day must not be empty.")
    if len(day) > 255:
        raise ValueError("day must be <= 255 chars.")
    if ".." in day:
        raise ValueError("day cannot contain ..")
    if "/" in day:
        raise ValueError("day cannot contain /")
    if "\\" in day:
        raise ValueError("day cannot contain \\")
    if "\x00" in day:
        raise ValueError("day cannot contain null bytes.")
    return day

async def get_wedge_state(uid: str) -> Optional[bool]:
    """Get the wedge state for the user."""
    try:
        uid = _clean_id(uid)
        day = _clean_day(str(date.today()))
        async with async_session() as session:
            result = await session.execute(
                func=get_wedge_state_func(),
                params={"uid": uid, "day": day}
            )
            return result
    except Exception as e:
        logger.error(f"Error in get_wedge_state: {e}")
        return None

async def reset_wedge_state(uid: str) -> bool:
    """Reset the wedge state for the user."""
    try:
        uid = _clean_id(uid)
        day = _clean_day(str(date.today()))
        async with async_session() as session:
            result = await session.execute(
                func=reset_wedge_state_func(),
                params={"uid": uid, "day": day}
            )
            return result
    except Exception as e:
        logger.error(f"Error in reset_wedge_state: {e}")
        return False

# Example usage:
# get_wedge_state("user123")  # Returns the state or None
# reset_wedge_state("user456")  # Returns True or False
```

This code includes the _clean_id and _clean_day functions for input validation, the get_wedge_state and reset_wedge_state functions with try-except blocks for error handling, and ensures atomic transactions are wrapped in defensive boundaries.