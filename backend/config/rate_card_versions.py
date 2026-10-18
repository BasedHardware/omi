"""Reviewed content identities. A published card revision requires a new version file.

The independent literal in test_rate_card pins this registry as well as the bytes.
V1 remains the default; v2 is opt-in through RATE_CARD_VERSION.
"""

from typing import Final

RATE_CARD_SHA256: Final[dict[str, str]] = {
    'v1': '782edb7e64afdd72be88e81d03cc7346b46df332881de836a5e7cd6fe8ae32a0',
    'v2': '1243f8029abe7e4c2378cb0ec666ea993379cf5598b8a6e7bc4309f65c7e956f',
}
