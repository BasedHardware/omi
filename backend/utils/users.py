from database.auth import get_user_name


def get_user_display_name(uid: str, default: str = 'Someone') -> str:
    """Get a user's display name from Firebase Auth.

    Uses the same Firebase Auth lookup as the rest of the codebase
    (see database/auth.py:get_user_name), returning the user's first name.
    Falls back to the provided default if no name is found.
    """
    name = get_user_name(uid, use_default=False)
    return name or default
