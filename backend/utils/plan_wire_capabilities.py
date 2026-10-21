"""Decoder capability selects labels only; it never selects entitlements.

X-Omi-Plan-Identity: 1 declares the six catalog IDs and lossless unknown-plan
handling without inferring paid access. Missing capabilities use release floors.
"""

import os
from typing import Callable, Optional

MIN_MOBILE_VERSION = os.getenv('PLUS_UNLIMITED_V2_MIN_MOBILE_VERSION', '99.0.0')
# v0.12.197+12197-macos published the decoder; v0.12.196 lacks Plus/unknown.
MIN_MACOS_VERSION = os.getenv('PLUS_UNLIMITED_V2_MIN_DESKTOP_VERSION', '0.12.197')
# macOS releases cannot establish safe decoding for Windows builds.
MIN_WINDOWS_VERSION = os.getenv('PLUS_UNLIMITED_V2_MIN_WINDOWS_VERSION', '99.0.0')


def understands_plan_identity(
    platform: Optional[str],
    app_version: Optional[str],
    identity_version: Optional[str],
    compare_versions: Callable[[str, str], int],
) -> bool:
    floors = {
        'ios': MIN_MOBILE_VERSION,
        'android': MIN_MOBILE_VERSION,
        'macos': MIN_MACOS_VERSION,
        'windows': MIN_WINDOWS_VERSION,
        'web': '0.1.0',
    }
    if os.getenv('LADDER_V1_WIRE_IDENTITY_ENABLED', 'false') == 'true':
        # Floors must be approved shipped decoder versions; absent configuration preserves the old floor.
        floors.update(
            {
                'ios': os.getenv('LADDER_V1_MIN_MOBILE_VERSION', MIN_MOBILE_VERSION),
                'android': os.getenv('LADDER_V1_MIN_MOBILE_VERSION', MIN_MOBILE_VERSION),
                'windows': os.getenv('LADDER_V1_MIN_WINDOWS_VERSION', MIN_WINDOWS_VERSION),
            }
        )
    platform_key = (platform or '').lower()
    if platform_key not in floors:
        return False
    if identity_version == '1':
        return True
    if not app_version:
        return False
    try:
        return compare_versions(app_version, floors[platform_key]) >= 0
    except Exception:
        return False
