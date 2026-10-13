"""Reviewed content identities. A published card revision requires a new version file.

The independent literal in test_rate_card pins this registry as well as the bytes.
V1 is finalized in its draft before any production projection or release.
"""

from typing import Final

RATE_CARD_SHA256: Final[dict[str, str]] = {
    'v1': '782edb7e64afdd72be88e81d03cc7346b46df332881de836a5e7cd6fe8ae32a0',
}
