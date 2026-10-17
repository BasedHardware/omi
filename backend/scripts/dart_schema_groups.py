"""Schema-group metadata kept outside the oversized Dart generator."""

from pathlib import Path
from typing import Any


def additional_schema_groups(output_dir: Path) -> dict[str, dict[str, Any]]:
    return {
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
                'StorefrontCurrent',
                'StorefrontPrice',
                'StorefrontResponse',
                'StorefrontTier',
                'StorefrontUsage',
            ),
        },
        'affiliate': {
            'output': output_dir / 'affiliate_wire.g.dart',
            'schemas': (
                'AffiliateStatusResponse',
                'AffiliateProfile',
                'AffiliateLinkCredentialsRequest',
                'AffiliateLinkResponse',
                'AffiliateStatsResponse',
                'AffiliateOrder',
                'AffiliateOrdersResponse',
                'AffiliateTransaction',
                'AffiliateCommission',
                'AffiliateEarningsResponse',
                'AffiliatePayout',
                'AffiliatePayoutsResponse',
                'AffiliateRefCodeAvailabilityResponse',
                'AffiliateRefCodeUpdateRequest',
                'AffiliateRefCodeUpdateResponse',
                'AffiliatePayoutSetupRequest',
                'AffiliatePayoutLinkResponse',
                'AffiliatePayoutAccountStatusResponse',
            ),
        },
    }
