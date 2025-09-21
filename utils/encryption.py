import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Load the master secret from environment variables. This must be a securely managed 32-byte key.
ENCRYPTION_SECRET = os.getenv('ENCRYPTION_SECRET', '').encode('utf-8')
if not ENCRYPTION_SECRET or len(ENCRYPTION_SECRET) < 32:
    raise ValueError(
        "ENCRYPTION_SECRET environment variable not set or is too short. " "It must be a securely managed 32-byte key."
    )


def derive_key(uid: str) -> bytes:
    """
    Derives a user-specific 32-byte key from the master secret and user ID (salt).
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=uid.encode('utf-8'),
        info=b'user-data-encryption',
    )
    return hkdf.derive(ENCRYPTION_SECRET)


def encrypt(data: str, uid: str) -> str:
    """
    Encrypts a string using a user-specific key.
    Returns a base64 encoded string containing nonce + ciphertext + tag.
    """
    if not data:
        return data
    key = derive_key(uid)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # GCM standard nonce size

    # Data must be bytes
    plaintext_bytes = data.encode('utf-8')

    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    # Combine nonce and ciphertext for storage
    encrypted_payload = nonce + ciphertext

    return base64.b64encode(encrypted_payload).decode('utf-8')


def decrypt(encrypted_data: str, uid: str) -> str:
    """
    Decrypts a base64 encoded string using a user-specific key.
    """
    if not encrypted_data or not isinstance(encrypted_data, str):
        return encrypted_data

    try:
        key = derive_key(uid)
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
        print(f"Decryption failed for user {uid}: {e}")
        return encrypted_data
