import base64
import os
import struct
import threading

from cachetools import TTLCache
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import logging

logger = logging.getLogger(__name__)

# Load the master secret from environment variables. This must be a securely managed 32-byte key.
ENCRYPTION_SECRET = os.getenv('ENCRYPTION_SECRET', '').encode('utf-8')
if not ENCRYPTION_SECRET or len(ENCRYPTION_SECRET) < 32:
    raise ValueError(
        "ENCRYPTION_SECRET environment variable not set or is too short. " "It must be a securely managed 32-byte key."
    )

# HKDF ``info`` values. Each purpose gets its own key from the same master secret and uid, so a
# ciphertext made for one purpose never decrypts under another. Everything stored before purposes
# existed is user data, which is why it is the default.
USER_DATA_KEY_PURPOSE = b'user-data-encryption'

_DERIVED_KEY_CACHE: TTLCache[tuple[bytes, str], bytes] = TTLCache(maxsize=10_000, ttl=86_400)
_DERIVED_KEY_LOCK = threading.Lock()


def derive_key(uid: str, *, purpose: bytes = USER_DATA_KEY_PURPOSE) -> bytes:
    """
    Derives a user-specific 32-byte key from the master secret and user ID (salt) for one purpose.
    """
    cache_key = (purpose, uid)
    with _DERIVED_KEY_LOCK:
        cached = _DERIVED_KEY_CACHE.get(cache_key)
        if cached is not None:
            return cached

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=uid.encode('utf-8'),
        info=purpose,
    )
    key = hkdf.derive(ENCRYPTION_SECRET)
    with _DERIVED_KEY_LOCK:
        _DERIVED_KEY_CACHE[cache_key] = key
    return key


def clear_derived_key_cache() -> None:
    with _DERIVED_KEY_LOCK:
        _DERIVED_KEY_CACHE.clear()


def encrypt(data: str, uid: str, *, purpose: bytes = USER_DATA_KEY_PURPOSE) -> str:
    """
    Encrypts a string using a user-specific key for ``purpose``.
    Returns a base64 encoded string containing nonce + ciphertext + tag.
    """
    if not data:
        return data
    key = derive_key(uid, purpose=purpose)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # GCM standard nonce size

    # Data must be bytes
    plaintext_bytes = data.encode('utf-8')

    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    # Combine nonce and ciphertext for storage
    encrypted_payload = nonce + ciphertext

    return base64.b64encode(encrypted_payload).decode('utf-8')


def decrypt(encrypted_data: str, uid: str, *, purpose: bytes = USER_DATA_KEY_PURPOSE) -> str:
    """
    Decrypts a base64 encoded string using a user-specific key for ``purpose``.
    """
    if not encrypted_data:
        return encrypted_data

    try:
        key = derive_key(uid, purpose=purpose)
        aesgcm = AESGCM(key)

        encrypted_payload = base64.b64decode(encrypted_data.encode('utf-8'))

        # Extract nonce and ciphertext
        nonce = encrypted_payload[:12]
        ciphertext = encrypted_payload[12:]

        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)

        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        # If decryption fails (e.g., wrong key, corrupted data), return the original encrypted data
        # to avoid data loss and to make debugging easier. In a production system, you might want
        # to log this error.
        logger.error(f"Decryption failed for user {uid}: {e}")
        return encrypted_data


def encrypt_audio_chunk(data: bytes, uid: str) -> bytes:
    """
    Encrypt audio chunk and return length-prefixed binary format.
    Format: [4 bytes length][12 bytes nonce][ciphertext + tag]

    This format allows concatenating multiple encrypted chunks without decryption.
    """
    key = derive_key(uid)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)

    # Encrypt (includes authentication tag)
    ciphertext = aesgcm.encrypt(nonce, data, None)

    # Combine nonce + ciphertext
    encrypted_payload = nonce + ciphertext

    # Add length prefix (4 bytes, big-endian)
    length = len(encrypted_payload)
    return struct.pack('>I', length) + encrypted_payload


def decrypt_audio_chunk(encrypted_data: bytes, uid: str, offset: int = 0):
    """
    Decrypt a single length-prefixed chunk.
    Returns: (decrypted_data, bytes_consumed)
    """
    # Read length prefix
    length = struct.unpack('>I', encrypted_data[offset : offset + 4])[0]
    offset += 4

    # Extract encrypted payload
    encrypted_payload = encrypted_data[offset : offset + length]

    # Extract nonce and ciphertext
    nonce = encrypted_payload[:12]
    ciphertext = encrypted_payload[12:]

    # Decrypt
    key = derive_key(uid)
    aesgcm = AESGCM(key)
    decrypted = aesgcm.decrypt(nonce, ciphertext, None)

    return decrypted, 4 + length


def decrypt_audio_file(encrypted_data: bytes, uid: str) -> bytes:
    """
    Decrypt an entire merged audio file (multiple concatenated chunks).
    Each chunk is length-prefixed, allowing simple concatenation during merge.
    """
    decrypted_audio = bytearray()
    offset = 0

    while offset < len(encrypted_data):
        chunk_data, bytes_consumed = decrypt_audio_chunk(encrypted_data, uid, offset)
        decrypted_audio.extend(chunk_data)
        offset += bytes_consumed

    return bytes(decrypted_audio)
