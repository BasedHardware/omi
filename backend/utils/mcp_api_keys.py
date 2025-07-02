import hashlib
import secrets
from typing import Tuple

API_KEY_PREFIX_LENGTH = 8
API_KEY_LENGTH = 32


def generate_api_key() -> Tuple[str, str]:
    """
    Generates a new API key.
    Returns a tuple of (key_prefix, api_key).
    """
    api_key = secrets.token_urlsafe(API_KEY_LENGTH)
    return api_key[:API_KEY_PREFIX_LENGTH], api_key


def hash_api_key(api_key: str) -> str:
    """
    Hashes an API key using SHA256.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()
