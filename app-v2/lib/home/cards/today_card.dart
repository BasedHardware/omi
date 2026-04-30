import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/cards/card_entrance.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// "Today" surface card — the one place on Home that lists pending action
/// items. Replaces the per-item action item card to break the stacked-cards
/// anti-pattern called out in the design doc. Up to 3 bullets; "See all"
/// links to the Plan tab where bulk action lives.
final class TodayCard extends CompanionCard {
  TodayCard({
    required this.descriptions,
    required this.generatedAt,
  });

  /// Up to 3 plain-text descriptions, newest first. Empty list renders the
  /// Day-1 explainer copy in place of bullets.
  final List<String> descriptions;

  @override
  final DateTime generatedAt;

  @override
  String get id => _stableId;

  @override
  CardKind get kind => CardKind.actionItem;

  @override
  int get priority => 500;

  /// Refreshes on every Home foreground anyway, so a short TTL keeps stale
  /// rows from lingering after a long background.
  @override
  Duration get ttl => const Duration(hours: 6);

  @override
  Map<String, dynamic> toJson() => {
        'kind': kind.code,
        'descriptions': descriptions,
        'generatedAt': generatedAt.toIso8601String(),
      };

  factory TodayCard.fromJson(Map<String, dynamic> json) {
    return TodayCard(
      descriptions: ((json['descriptions'] as List<dynamic>?) ?? const [])
          .cast<String>(),
      generatedAt: DateTime.parse(json['generatedAt'] as String),
    );
  }

  @override
  void onAction(BuildContext context, CardAction action) {
    // No inline accept/snooze/dismiss — bulk action lives on the Plan tab.
    // tapThrough/open both route to Plan.
    if (action == CardAction.tapThrough || action == CardAction.open) {
      context.read<HomeNav>().switchToTab(HomeNav.planTabIndex);
    }
  }

  @override
  Widget render(BuildContext context) => _TodayCardView(card: this);

  static const String _stableId = 'today:summary';
}

/// Generator. Returns null while the provider is still on its first fetch so
/// Home doesn't flash an empty Today card before data arrives. Once `ready`,
/// emits the card whether or not there are items — the empty state IS the
/// Day-1 explainer per the design doc.
TodayCard? todayCardFor(ActionItemsProvider provider) {
  if (!provider.ready) return null;
  return TodayCard(
    descriptions:
        provider.incompleteTop3.map((i) => i.description).toList(growable: false),
    generatedAt: DateTime.now(),
  );
}

class _TodayCardView extends StatelessWidget {
  const _TodayCardView({required this.card});

  final TodayCard card;

  @override
  Widget build(BuildContext context) {
    final hasItems = card.descriptions.isNotEmpty;
    return CardEntrance(
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.backgroundSecondary,
          borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        padding: const EdgeInsets.all(AppStyles.spacingL),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Today',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: AppStyles.spacingM),
            if (hasItems)
              for (var i = 0; i < card.descriptions.length; i++) ...[
                _Bullet(text: card.descriptions[i]),
                if (i < card.descriptions.length - 1)
                  const SizedBox(height: AppStyles.spacingS),
              ]
            else
              const Text(
                "Once you start a recording I'll surface what you committed "
                'to here.',
                style: TextStyle(
                  fontSize: 14,
                  color: AppColors.textTertiary,
                  height: 1.4,
                ),
              ),
            const SizedBox(height: AppStyles.spacingM),
            _SeeAllRow(
              enabled: hasItems,
              onTap: () => card.onAction(context, CardAction.tapThrough),
            ),
          ],
        ),
      ),
    );
  }
}

class _Bullet extends StatelessWidget {
  const _Bullet({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 7),
          child: Container(
            width: 6,
            height: 6,
            decoration: const BoxDecoration(
              color: AppColors.brandPrimary,
              shape: BoxShape.circle,
            ),
          ),
        ),
        const SizedBox(width: AppStyles.spacingM),
        Expanded(
          child: Text(
            text,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 14,
              color: AppColors.textSecondary,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}

class _SeeAllRow extends StatelessWidget {
  const _SeeAllRow({required this.enabled, required this.onTap});
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = enabled ? AppColors.textTertiary : AppColors.textTertiary.withValues(alpha: 0.5);
    final row = Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Text(
          'See all',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: color,
          ),
        ),
        const SizedBox(width: AppStyles.spacingXS),
        Icon(Icons.arrow_forward_rounded, size: 16, color: color),
      ],
    );
    if (!enabled) return row;
    return Semantics(
      button: true,
      label: 'See all action items, opens Plan tab',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingXS),
          child: row,
        ),
      ),
    );
  }
}
