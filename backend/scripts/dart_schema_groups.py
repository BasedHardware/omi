"""Schema-group metadata kept outside the oversized Dart generator."""

from pathlib import Path
from typing import Any


def additional_schema_groups(output_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        'referrals': {
            'output': output_dir / 'referrals_wire.g.dart',
            'schemas': ('ReferralLinkResponse', 'CampaignSnapshotResponse', 'CampaignAttributionResponse'),
        },
        'recording_speakers': {
            'output': output_dir / 'recording_speakers_wire.g.dart',
            'schemas': (
                'RecordingTranscriptResponse',
                'RecordingTranscriptMember',
                'RecordingTranscriptSegment',
                'RecordingSpeakerResponse',
                'RecordingMemberCount',
                'Translation',
            ),
        },
        'goals': {
            'output': output_dir / 'goals_wire.g.dart',
            'schemas': (
                'GoalMetric',
                'GoalResponse',
                'GoalSuggestionResponse',
                'AdviceResponse',
                'GoalHistoryEntryResponse',
                'GoalDeleteResponse',
            ),
        },
        'storefront': {
            'output': output_dir / 'storefront_wire.g.dart',
            'schemas': (
                'ChatAtCap',
                'StorefrontCapChoice',
                'StorefrontCurrent',
                'StorefrontPrice',
                'StorefrontResponse',
                'StorefrontTier',
                'StorefrontUsage',
            ),
        },
    }
