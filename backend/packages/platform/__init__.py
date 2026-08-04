"""Platform primitives — re-export stable utils until full extract.

New platform code should land in this package; callers may import from here.
Edge TS twin lives under edge/packages/platform in the monorepo.
"""

from utils.encryption import (
    decrypt,
    decrypt_audio_chunk,
    decrypt_audio_file,
    derive_key,
    encrypt,
    encrypt_audio_chunk,
)
from utils.log_sanitizer import sanitize, sanitize_pii

__all__ = [
    "decrypt",
    "decrypt_audio_chunk",
    "decrypt_audio_file",
    "derive_key",
    "encrypt",
    "encrypt_audio_chunk",
    "sanitize",
    "sanitize_pii",
]
