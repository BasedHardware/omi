import inspect
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, cast

from database import users as users_db, redis_db
import logging

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _typed_doc(raw: object) -> Dict[str, Any]:
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _get_user_profile_for_data_protection(uid: str, firestore_client: Any = None) -> Dict[str, Any]:
    if firestore_client is not None:
        user_ref = firestore_client.collection('users').document(uid)
        user_doc = user_ref.get()
        if getattr(user_doc, "exists", False):
            raw: object = user_doc.to_dict()
            return _typed_doc(raw)
        return {}

    return users_db.get_user_profile(uid)


def set_data_protection_level(data_arg_name: str) -> Callable[[F], F]:
    """
    Decorator to automatically set 'data_protection_level' on a dictionary or a list of dictionaries.

    It retrieves the user's current data protection level from cache or DB and adds it to the data dictionary
    (or each dictionary in a list). This ensures that all data written to the database has the
    correct protection level set, abstracting this logic away from the individual database functions.

    Assumes 'uid' is an argument to the decorated function.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
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
            data: Any = bound_args.arguments.get(data_arg_name)

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
                data_dict: Dict[str, Any] = cast(Dict[str, Any], data)
                if data_dict.get('data_protection_level') is None:
                    needs_backfill = True
            else:
                data_list: List[Any] = cast(List[Any], data)
                for item in data_list:
                    if isinstance(item, dict):
                        item_dict: Dict[str, Any] = cast(Dict[str, Any], item)
                        if item_dict.get('data_protection_level') is None:
                            needs_backfill = True
                            break

            if not needs_backfill:
                return func(*args, **kwargs)

            firestore_client = bound_args.arguments.get('firestore_client')
            level: Optional[str] = (
                None if firestore_client is not None else redis_db.get_user_data_protection_level(uid)
            )

            if not level:
                try:
                    user_profile = _get_user_profile_for_data_protection(uid, firestore_client=firestore_client)
                    level = user_profile.get('data_protection_level', 'enhanced') if user_profile else 'enhanced'
                    if firestore_client is None:
                        redis_db.set_user_data_protection_level(uid, level)
                except Exception as e:
                    logger.error(f"Failed to get user profile for {uid}: {e}")
                    level = 'enhanced'

            if not level:
                level = 'enhanced'

            if isinstance(data, dict):
                data_dict_after: Dict[str, Any] = cast(Dict[str, Any], data)
                if data_dict_after.get('data_protection_level') is None:
                    data_dict_after['data_protection_level'] = level
            else:
                items_after: List[Any] = cast(List[Any], data)
                for item in items_after:
                    if isinstance(item, dict):
                        item_dict_after: Dict[str, Any] = cast(Dict[str, Any], item)
                        if item_dict_after.get('data_protection_level') is None:
                            item_dict_after['data_protection_level'] = level

            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def prepare_for_write(
    data_arg_name: str,
    prepare_func: Callable[[Dict[str, Any], str, str], Dict[str, Any]],
    *,
    preserve_result: bool = False,
) -> Callable[[F], F]:
    """
    Decorator to prepare data before writing to the database.
    It uses the provided prepare_func to handle the specifics of data preparation,
    such as compression or encryption, based on the data's protection level.
    By default the decorated function's return value is ignored and the decorator
    returns the original, unencrypted data.  Callers that need a transactional
    admission result can opt into ``preserve_result``.

    Assumes 'uid' and the data dictionary (specified by data_arg_name) are arguments
    to the decorated function. Also assumes 'data_protection_level' is already set on the data.
    This decorator should be placed AFTER @set_data_protection_level.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            uid = bound_args.arguments.get('uid')
            original_data: Any = bound_args.arguments.get(data_arg_name)

            if not uid:
                raise TypeError(
                    f"Function {func.__name__} decorated with prepare_for_write must have a 'uid' argument."
                )

            if not isinstance(original_data, (dict, list)):
                result = func(*args, **kwargs)
                return result if preserve_result else original_data

            prepared_data: Any = cast(Any, original_data)

            if isinstance(original_data, dict):
                data_dict: Dict[str, Any] = cast(Dict[str, Any], original_data)
                level_value = data_dict.get('data_protection_level', 'standard')
                prepared_data = prepare_func(
                    data_dict, uid, str(level_value) if level_value is not None else 'standard'
                )
            else:
                items: List[Any] = cast(List[Any], original_data)
                if items and isinstance(items[0], dict):
                    prepared_list: List[Dict[str, Any]] = []
                    for item in items:
                        if isinstance(item, dict):
                            item_dict = cast(Dict[str, Any], item)
                            level_value = item_dict.get('data_protection_level', 'standard')
                            prepared_list.append(
                                prepare_func(
                                    item_dict, uid, str(level_value) if level_value is not None else 'standard'
                                )
                            )
                    prepared_data = prepared_list

            # Modify the bound arguments with the prepared data and reconstruct the call
            bound_args.arguments[data_arg_name] = prepared_data
            result = func(*bound_args.args, **bound_args.kwargs)

            # Return the original, unmodified data from the initial call
            return result if preserve_result else cast(Any, original_data)

        return cast(F, wrapper)

    return decorator


def prepare_for_read(decrypt_func: Callable[[Dict[str, Any], str], Dict[str, Any]]) -> Callable[[F], F]:
    """
    Decorator to decrypt data after reading from the database.
    It processes the return value of the decorated function. If the return value is a dict or
    list of dicts, it applies the decrypt_func based on the 'data_protection_level' field.

    Assumes 'uid' is an argument to the decorated function to be used for decryption.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            uid = bound_args.arguments.get('uid')
            if not uid:
                raise TypeError(f"Function {func.__name__} decorated with prepare_for_read must have a 'uid' argument.")

            result = func(*args, **kwargs)

            if result is None:
                return None

            def _process(item: Any) -> Any:
                if isinstance(item, dict):
                    # The decrypt_func is responsible for checking the level and acting accordingly
                    return decrypt_func(cast(Dict[str, Any], item), uid)
                return item

            if isinstance(result, dict):
                return _process(result)
            elif isinstance(result, list):
                items: List[Any] = cast(List[Any], result)
                return [_process(item) for item in items]
            elif isinstance(result, tuple):
                # Handle functions that return a tuple, e.g., (data, doc_id)
                elements: Tuple[Any, ...] = cast(Tuple[Any, ...], result)
                processed_elements: List[Any] = []
                for element in elements:
                    if isinstance(element, dict):
                        processed_elements.append(_process(element))
                    elif isinstance(element, list):
                        processed_elements.append([_process(item) for item in cast(List[Any], element)])
                    else:
                        processed_elements.append(element)
                return tuple(processed_elements)
            return result

        return cast(F, wrapper)

    return decorator


def with_photos(photos_getter: Callable[..., Any]) -> Callable[[F], F]:
    """
    Decorator to automatically populate the 'photos' field for a conversation or a list of conversations.
    It fetches documents from the 'photos' sub-collection and attaches them using the provided getter.
    This should be applied to functions that return conversation dicts and have a 'uid' parameter.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
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

            def _fetch_and_attach_photos(conversation_data: Any) -> Any:
                if not isinstance(conversation_data, dict) or 'id' not in conversation_data:
                    return cast(Any, conversation_data)

                data_dict: Dict[str, Any] = cast(Dict[str, Any], conversation_data)

                # If photos are already present and not empty, don't overwrite.
                # This handles cases where photos are added in-memory before DB retrieval.
                if data_dict.get('photos'):
                    return data_dict

                conversation_id = data_dict['id']
                photos = photos_getter(uid=uid, conversation_id=conversation_id)
                data_dict['photos'] = photos
                return data_dict

            if isinstance(result, dict):
                return _fetch_and_attach_photos(result)
            elif isinstance(result, list):
                items: List[Any] = cast(List[Any], result)
                return [_fetch_and_attach_photos(item) for item in items]
            elif isinstance(result, tuple):
                elements: Tuple[Any, ...] = cast(Tuple[Any, ...], result)
                processed_elements: List[Any] = []
                for element in elements:
                    if isinstance(element, dict):
                        processed_elements.append(_fetch_and_attach_photos(element))
                    elif isinstance(element, list):
                        processed_elements.append([_fetch_and_attach_photos(item) for item in cast(List[Any], element)])
                    else:
                        processed_elements.append(element)
                return tuple(processed_elements)

            return result

        return cast(F, wrapper)

    return decorator
