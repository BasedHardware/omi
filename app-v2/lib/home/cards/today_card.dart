import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/cards/card_entrance.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// One pending commitment shown in the Today surface card.
///
/// Stays a flat data class on purpose — actions live in the Plan tab per the
/// design doc. Fields beyond `description` are optional so a generator can
/// emit minimal items when the source schema doesn't carry timing.
class TodayItem {
  const TodayItem({
    required this.description,
    this.createdAt,
    this.dueAt,
  });

  final String description;
  final DateTime? createdAt;
  final DateTime? dueAt;

  Map<String, dynamic> toJson() => {
        'description': description,
        if (createdAt != null) 'createdAt': createdAt!.toIso8601String(),
        if (dueAt != null) 'dueAt': dueAt!.toIso8601String(),
      };

  factory TodayItem.fromJson(Map<String, dynamic> json) {
    return TodayItem(
      description: json['description'] as String? ?? '',
      createdAt: json['createdAt'] != null
          ? DateTime.tryParse(json['createdAt'] as String)
          : null,
      dueAt: json['dueAt'] != null
          ? DateTime.tryParse(json['dueAt'] as String)
          : null,
    );
  }
}

/// "Today" surface card — the one place on Home that lists pending action
/// items. Replaces the per-item action item card to break the stacked-cards
/// anti-pattern called out in the design doc. Up to 3 bullets; "See all"
/// links to the Plan tab where bulk action lives.
final class TodayCard extends CompanionCard {
  TodayCard({
    required this.items,
    required this.generatedAt,
    this.totalIncomplete,
  });

  /// Up to 3 visible items, newest first. Empty list renders the Day-1
  /// explainer copy in place of bullets.
  final List<TodayItem> items;

  /// Total incomplete items across the user's list (not just the top 3).
  /// Drives the "3 of 12" subtitle when there's more than what we render.
  /// Null = unknown (older cached cards before this field was added).
  final int? totalIncomplete;

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
        'items': items.map((i) => i.toJson()).toList(),
        if (totalIncomplete != null) 'totalIncomplete': totalIncomplete,
        'generatedAt': generatedAt.toIso8601String(),
      };

  factory TodayCard.fromJson(Map<String, dynamic> json) {
    // Read the rich `items` list when present, otherwise fall back to legacy
    // `descriptions` rows from cards cached before TodayItem existed.
    final rawItems = json['items'] as List<dynamic>?;
    final items = rawItems != null
        ? rawItems
            .map((e) => TodayItem.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList()
        : ((json['descriptions'] as List<dynamic>?) ?? const [])
            .cast<String>()
            .map((d) => TodayItem(description: d))
            .toList();
    return TodayCard(
      items: items,
      totalIncomplete: json['totalIncomplete'] as int?,
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
    items: provider.incompleteTop3
        .map((i) => TodayItem(
              description: i.description,
              createdAt: i.createdAt,
              dueAt: i.dueAt,
            ))
        .toList(growable: false),
    totalIncomplete: provider.items.length,
    generatedAt: DateTime.now(),
  );
}

class _TodayCardView extends StatelessWidget {
  const _TodayCardView({required this.card});

  final TodayCard card;

  @override
  Widget build(BuildContext context) {
    final hasItems = card.items.isNotEmpty;
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
            _Header(card: card),
            const SizedBox(height: AppStyles.spacingM),
            if (hasItems)
              for (var i = 0; i < card.items.length; i++) ...[
                _Bullet(item: card.items[i]),
                if (i < card.items.length - 1)
                  const SizedBox(height: AppStyles.spacingM),
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

class _Header extends StatelessWidget {
  const _Header({required this.card});
  final TodayCard card;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final visible = card.items.length;
    final total = card.totalIncomplete;
    final dateLabel = MaterialLocalizations.of(context).formatShortDate(card.generatedAt);
    final subtitle = _buildSubtitle(l: l, visible: visible, total: total, dateLabel: dateLabel);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          l.todayCardHeader,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 2),
          Text(
            subtitle,
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.textTertiary,
            ),
          ),
        ],
      ],
    );
  }

  String? _buildSubtitle({
    required AppLocalizations l,
    required int visible,
    required int? total,
    required String dateLabel,
  }) {
    if (visible == 0) return dateLabel;
    if (total != null && total > visible) {
      return '$dateLabel · ${l.todayCardCountPartial(visible, total)}';
    }
    return '$dateLabel · ${l.todayCardCountFull(visible)}';
  }
}

class _Bullet extends StatelessWidget {
  const _Bullet({required this.item});
  final TodayItem item;

  @override
  Widget build(BuildContext context) {
    final trailing = _trailingLabel(item);
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
            item.description,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 14,
              color: AppColors.textSecondary,
              height: 1.4,
            ),
          ),
        ),
        if (trailing != null) ...[
          const SizedBox(width: AppStyles.spacingS),
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              trailing,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w500,
                color: AppColors.textQuaternary,
              ),
            ),
          ),
        ],
      ],
    );
  }

  /// Trailing time tag. Due dates take priority since they're actionable;
  /// otherwise we surface the item's age so the user can tell which
  /// commitments are getting stale. Returns null when there's nothing
  /// meaningful to show (rare: items always have createdAt from the server).
  String? _trailingLabel(TodayItem item) {
    final due = item.dueAt;
    if (due != null) {
      final delta = due.difference(DateTime.now());
      if (delta.isNegative) return 'overdue';
      if (delta.inHours < 24) return 'due ${delta.inHours}h';
      if (delta.inDays < 7) return 'due ${delta.inDays}d';
      return 'due soon';
    }
    final created = item.createdAt;
    if (created == null) return null;
    final age = DateTime.now().difference(created);
    if (age.inMinutes < 60) return 'just now';
    if (age.inHours < 24) return '${age.inHours}h';
    if (age.inDays < 30) return '${age.inDays}d';
    return '${(age.inDays / 30).floor()}mo';
  }
}

class _SeeAllRow extends StatelessWidget {
  const _SeeAllRow({required this.enabled, required this.onTap});
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // Brand-blue when enabled — matches the bullet dots and signals this is
    // the gateway to Plan tab. Quieter textTertiary in the disabled empty
    // state where there's nothing to navigate to.
    final l = AppLocalizations.of(context);
    final color = enabled
        ? AppColors.brandPrimary
        : AppColors.textTertiary.withValues(alpha: 0.5);
    final row = Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Text(
          l.todayCardSeeAll,
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
      label: l.todayCardSeeAllSemantics,
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
