import hashlib
import secrets
from typing import Tuple


def generate_dev_api_key() -> Tuple[str, str, str]:
    """
    Generates a new Developer API key.
    Returns a tuple of (raw_key, hashed_key, key_prefix).
    """
    secret_part = secrets.token_hex(16)
    raw_key = f"omi_dev_{secret_part}"
    hashed_key = hash_dev_api_key(secret_part)
    key_prefix = f"omi_dev_{secret_part[:4]}...{secret_part[-4:]}"
    return raw_key, hashed_key, key_prefix


def hash_dev_api_key(api_key: str) -> str:
    """
    Hashes an API key using SHA256.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()
