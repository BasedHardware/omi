import inspect
from functools import wraps
from typing import List, Dict, Any, Callable

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


def prepare_for_write(data_arg_name: str, encrypt_func: Callable[[Dict[str, Any], str], Dict[str, Any]]):
    """
    Decorator to encrypt data before writing to the database if protection level is 'enhanced'.
    It uses the provided encrypt_func to handle the specifics of which fields to encrypt.
    The decorated function's return value is ignored; the decorator returns the original, unencrypted data.

    Assumes 'uid' and the data dictionary (specified by data_arg_name) are arguments
    to the decorated function. Also assumes 'data_protection_level' is already set on the data.
    This decorator should be placed AFTER @set_data_protection_level.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            uid = bound_args.arguments.get('uid')
            original_data = bound_args.arguments.get(data_arg_name)

            if not uid:
                raise TypeError(f"Function {func.__name__} decorated with prepare_for_write must have a 'uid' argument.")

            if not isinstance(original_data, (dict, list)):
                func(*args, **kwargs)
                return original_data

            # This decorator modifies the arguments for the wrapped function.
            # We need to create a new dictionary for kwargs to avoid modifying the original.
            new_kwargs = kwargs.copy()
            prepared_data = original_data

            if isinstance(original_data, dict):
                level = original_data.get('data_protection_level', 'standard')
                if level == 'enhanced':
                    prepared_data = encrypt_func(original_data, uid)  # encrypt_func should handle copying
            elif isinstance(original_data, list):
                if original_data and isinstance(original_data[0], dict):
                    level = original_data[0].get('data_protection_level', 'standard')
                    if level == 'enhanced':
                        prepared_data = [encrypt_func(item, uid) for item in original_data]

            new_kwargs[data_arg_name] = prepared_data
            func(*args, **new_kwargs)

            # Return the original, unmodified data from the initial call
            return original_data
        return wrapper
    return decorator


def prepare_for_read(decrypt_func: Callable[[Dict[str, Any], str], Dict[str, Any]]):
    """
    Decorator to decrypt data after reading from the database.
    It processes the return value of the decorated function. If the return value is a dict or
    list of dicts, it applies the decrypt_func based on the 'data_protection_level' field.

    Assumes 'uid' is an argument to the decorated function to be used for decryption.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            uid = bound_args.arguments.get('uid')
            if not uid:
                raise TypeError(f"Function {func.__name__} decorated with prepare_for_read must have a 'uid' argument.")

            # Execute the original function to get the data from the database
            result = func(*args, **kwargs)

            if result is None:
                return None

            def _process(item):
                if isinstance(item, dict):
                    level = item.get('data_protection_level')
                    if level == 'enhanced':
                        return decrypt_func(item, uid)
                return item

            if isinstance(result, dict):
                return _process(result)
            elif isinstance(result, list):
                return [_process(item) for item in result]
            elif isinstance(result, tuple):
                # Handle functions that return a tuple, e.g., (data, doc_id)
                processed_elements = []
                for element in result:
                    if isinstance(element, dict):
                        processed_elements.append(_process(element))
                    elif isinstance(element, list):
                        processed_elements.append([_process(item) for item in element])
                    else:
                        processed_elements.append(element)
                return tuple(processed_elements)

            return result
        return wrapper
    return decorator
