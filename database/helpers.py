import inspect
from functools import wraps
from typing import List, Dict, Any, Callable

from google.cloud import firestore

from database import users as users_db, redis_db
from ._client import db


def set_data_protection_level(data_arg_name: str):
    """
    Decorator to automatically set 'data_protection_level' on a dictionary or a list of dictionaries.

    It retrieves the user's current data protection level from cache or DB and adds it to the data dictionary
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
                raise TypeError(
                    f"Function {func.__name__} decorated with set_data_protection_level must have a 'uid' argument."
                )

            # If data is None or not a dict/list, do nothing and let the original function handle it.
            if not isinstance(data, (dict, list)):
                return func(*args, **kwargs)

            # Check if backfilling is needed before fetching the level from DB/cache for performance.
            needs_backfill = False
            if isinstance(data, dict):
                if data.get('data_protection_level') is None:
                    needs_backfill = True
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('data_protection_level') is None:
                        needs_backfill = True
                        break

            if not needs_backfill:
                return func(*args, **kwargs)

            level = redis_db.get_user_data_protection_level(uid)

            if not level:
                try:
                    user_profile = users_db.get_user_profile(uid)
                    level = user_profile.get('data_protection_level', 'standard') if user_profile else 'standard'
                    redis_db.set_user_data_protection_level(uid, level)
                except Exception as e:
                    print(f"Failed to get user profile for {uid}: {e}")
                    level = 'standard'

            if not level:
                level = 'standard'

            if isinstance(data, dict):
                if data.get('data_protection_level') is None:
                    data['data_protection_level'] = level
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if item.get('data_protection_level') is None:
                            item['data_protection_level'] = level

            return func(*args, **kwargs)

        return wrapper

    return decorator


def prepare_for_write(data_arg_name: str, prepare_func: Callable[[Dict[str, Any], str, str], Dict[str, Any]]):
    """
    Decorator to prepare data before writing to the database.
    It uses the provided prepare_func to handle the specifics of data preparation,
    such as compression or encryption, based on the data's protection level.
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
                raise TypeError(
                    f"Function {func.__name__} decorated with prepare_for_write must have a 'uid' argument."
                )

            if not isinstance(original_data, (dict, list)):
                func(*args, **kwargs)
                return original_data

            prepared_data = original_data

            if isinstance(original_data, dict):
                prepared_data = prepare_func(original_data, uid, original_data.get('data_protection_level', 'standard'))
            elif isinstance(original_data, list):
                if original_data and isinstance(original_data[0], dict):
                    prepared_data = [
                        prepare_func(item, uid, item.get('data_protection_level', 'standard')) for item in original_data
                    ]

            # Modify the bound arguments with the prepared data and reconstruct the call
            bound_args.arguments[data_arg_name] = prepared_data
            func(*bound_args.args, **bound_args.kwargs)

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

            result = func(*args, **kwargs)

            if result is None:
                return None

            def _process(item):
                if isinstance(item, dict):
                    # The decrypt_func is responsible for checking the level and acting accordingly
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


def with_photos(photos_getter: Callable):
    """
    Decorator to automatically populate the 'photos' field for a conversation or a list of conversations.
    It fetches documents from the 'photos' sub-collection and attaches them using the provided getter.
    This should be applied to functions that return conversation dicts and have a 'uid' parameter.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            uid = bound_args.arguments.get('uid')
            if not uid:
                raise TypeError(f"Function {func.__name__} decorated with with_photos must have a 'uid' argument.")

            # Execute the original function to get the conversation data
            result = func(*args, **kwargs)

            if result is None:
                return None

            def _fetch_and_attach_photos(conversation_data):
                if not isinstance(conversation_data, dict) or 'id' not in conversation_data:
                    return conversation_data

                # If photos are already present and not empty, don't overwrite.
                # This handles cases where photos are added in-memory before DB retrieval.
                if conversation_data.get('photos'):
                    return conversation_data

                conversation_id = conversation_data['id']
                photos = photos_getter(uid=uid, conversation_id=conversation_id)
                conversation_data['photos'] = photos
                return conversation_data

            if isinstance(result, dict):
                return _fetch_and_attach_photos(result)
            elif isinstance(result, list):
                return [_fetch_and_attach_photos(item) for item in result]
            elif isinstance(result, tuple):
                processed_elements = []
                for element in result:
                    if isinstance(element, dict):
                        processed_elements.append(_fetch_and_attach_photos(element))
                    elif isinstance(element, list):
                        processed_elements.append([_fetch_and_attach_photos(item) for item in element])
                    else:
                        processed_elements.append(element)
                return tuple(processed_elements)

            return result

        return wrapper

    return decorator
