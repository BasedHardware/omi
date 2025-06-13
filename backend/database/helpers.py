import inspect
from functools import wraps
from typing import List, Dict, Any

from database import users as users_db


def set_data_protection_level(data_arg_name: str):
    """
    Decorator to automatically set 'data_protection_level' on a dictionary or a list of dictionaries.

    It retrieves the user's current data protection level and adds it to the data dictionary
    (or each dictionary in a list). This ensures that all data written to the database has the
    correct protection level set, abstracting this logic away from the individual database functions.

    Assumes 'uid' is an argument to the decorated function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Bind the provided arguments to the function's signature to easily access them by name
            try:
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
            except TypeError:
                # This can happen if the decorated function is called with wrong arguments.
                # Let the original function call raise the more specific error.
                return func(*args, **kwargs)

            uid = bound_args.arguments.get('uid')
            data: Dict[str, Any] | List[Dict[str, Any]] | None = bound_args.arguments.get(data_arg_name)

            if not uid:
                raise TypeError(f"Function {func.__name__} decorated with set_data_protection_level must have a 'uid' argument.")

            # If data is None or not a dict/list, do nothing and let the original function handle it.
            if not isinstance(data, (dict, list)):
                return func(*args, **kwargs)

            current_level = users_db.get_data_protection_level(uid)

            if isinstance(data, dict):
                data['data_protection_level'] = current_level
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        item['data_protection_level'] = current_level

            # The arguments were modified in place, so we can just call the original function
            return func(*args, **kwargs)
        return wrapper
    return decorator
