"""Reviewed content identities. A published card revision requires a new version file.

The independent literal in test_rate_card pins this registry as well as the bytes.
V1 remains the default; v2 is opt-in through RATE_CARD_VERSION.
"""

from typing import Final

RATE_CARD_SHA256: Final[dict[str, str]] = {
    'v1': '782edb7e64afdd72be88e81d03cc7346b46df332881de836a5e7cd6fe8ae32a0',
    'v2': '292e2326d4d5009160cba7d0cb9921f9de8df3c0b6682af8da17fe29dc1e6b56',
}
