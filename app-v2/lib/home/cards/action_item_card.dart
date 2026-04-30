import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/companion/companion_signals.dart';
import 'package:nooto_v2/home/cards/card_entrance.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/companion_stream_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// A commitment the assistant heard the user make. Surface grammar — bordered
/// container with chrome — to contrast against voice cards (welcome, empty
/// state). Three actions: Done (accept), Snooze (24h), Dismiss.
///
/// Generator: [actionItemCardsFor]. Until the v2 backend is wired, this emits
/// a single demo card so we can validate the surface-card visual grammar
/// against the voice-grammar welcome card. Demo card has stable id so dismiss
/// sticks across launches.
final class ActionItemCard extends CompanionCard {
  ActionItemCard({
    required this.cardId,
    required this.title,
    required this.source,
    required this.capturedAt,
    required this.generatedAt,
  });

  final String cardId;
  final String title;

  /// Where the commitment was captured ("From your morning sync"). Empty
  /// string suppresses the source line.
  final String source;

  /// When the commitment was originally heard. Drives the relative time
  /// label ("12m ago", "2h ago"). Distinct from [generatedAt] which tracks
  /// when this card object was emitted into the stream.
  final DateTime capturedAt;

  @override
  final DateTime generatedAt;

  @override
  String get id => cardId;

  @override
  CardKind get kind => CardKind.actionItem;

  @override
  int get priority => 500;

  /// Action items go stale after a week if untouched — stops the stream from
  /// becoming a graveyard of forgotten promises.
  @override
  Duration get ttl => const Duration(days: 7);

  @override
  Map<String, dynamic> toJson() => {
        'kind': kind.code,
        'cardId': cardId,
        'title': title,
        'source': source,
        'capturedAt': capturedAt.toIso8601String(),
        'generatedAt': generatedAt.toIso8601String(),
      };

  factory ActionItemCard.fromJson(Map<String, dynamic> json) {
    return ActionItemCard(
      cardId: json['cardId'] as String,
      title: json['title'] as String? ?? '',
      source: json['source'] as String? ?? '',
      capturedAt: DateTime.parse(json['capturedAt'] as String),
      generatedAt: DateTime.parse(json['generatedAt'] as String),
    );
  }

  @override
  void onAction(BuildContext context, CardAction action) {
    final stream = context.read<CompanionStreamProvider>();
    if (action == CardAction.snooze) {
      stream.recordAction(
        this,
        action,
        snoozeUntil: DateTime.now().add(const Duration(hours: 24)),
      );
      return;
    }
    if (action == CardAction.accept || action == CardAction.dismiss) {
      stream.recordAction(this, action);
    }
  }

  @override
  Widget render(BuildContext context) => _ActionItemCardView(card: this);
}

/// Public generator. Returns a list so a future LLM-backed generator can emit
/// multiple action items in one pass without restructuring the call site.
///
/// Until the backend lands we emit a single fixed demo card so the
/// surface-card grammar is visible on Home. Stable id (`actionItem:demo:1`)
/// means dismiss persists across cold starts.
List<ActionItemCard> actionItemCardsFor(CompanionSignals signals) {
  return [
    ActionItemCard(
      cardId: 'actionItem:demo:1',
      title: 'Email John about the proposal',
      source: 'From your morning sync',
      capturedAt: DateTime.now().subtract(const Duration(minutes: 12)),
      generatedAt: DateTime.now(),
    ),
  ];
}

class _ActionItemCardView extends StatelessWidget {
  const _ActionItemCardView({required this.card});

  final ActionItemCard card;

  @override
  Widget build(BuildContext context) {
    final ago = _relativeTime(card.capturedAt);
    final showSource = card.source.trim().isNotEmpty;

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
            Row(
              children: [
                Text(
                  'Action item',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.4,
                    color: AppColors.brandPrimary.withValues(alpha: 0.9),
                  ),
                ),
                const Spacer(),
                Text(
                  ago,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textTertiary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppStyles.spacingS),
            Text(
              card.title,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: AppColors.textPrimary,
                height: 1.35,
              ),
            ),
            if (showSource) ...[
              const SizedBox(height: AppStyles.spacingXS),
              Text(
                card.source,
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textTertiary,
                ),
              ),
            ],
            const SizedBox(height: AppStyles.spacingM),
            Row(
              children: [
                _ActionButton(
                  label: 'Done',
                  icon: Icons.check_rounded,
                  primary: true,
                  onTap: () => card.onAction(context, CardAction.accept),
                ),
                const SizedBox(width: AppStyles.spacingS),
                _ActionButton(
                  label: 'Snooze',
                  icon: Icons.schedule_rounded,
                  onTap: () => card.onAction(context, CardAction.snooze),
                ),
                const Spacer(),
                Semantics(
                  button: true,
                  label: 'Dismiss action item',
                  child: SizedBox(
                    width: AppStyles.touchTargetMinimum,
                    height: AppStyles.touchTargetMinimum,
                    child: IconButton(
                      padding: EdgeInsets.zero,
                      icon: const Icon(
                        Icons.close_rounded,
                        size: 20,
                        color: AppColors.textTertiary,
                      ),
                      onPressed: () =>
                          card.onAction(context, CardAction.dismiss),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    required this.onTap,
    this.primary = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final fg = primary ? AppColors.brandPrimary : AppColors.textSecondary;
    final bg = primary
        ? AppColors.brandPrimary.withValues(alpha: 0.12)
        : Colors.white.withValues(alpha: 0.04);
    return Material(
      color: bg,
      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(
            minHeight: AppStyles.touchTargetMinimum,
          ),
          padding: const EdgeInsets.symmetric(
            horizontal: AppStyles.spacingM,
            vertical: AppStyles.spacingS,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 16, color: fg),
              const SizedBox(width: AppStyles.spacingXS + 2),
              Text(
                label,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: fg,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _relativeTime(DateTime t) {
  final delta = DateTime.now().difference(t);
  if (delta.inMinutes < 1) return 'just now';
  if (delta.inMinutes < 60) return '${delta.inMinutes}m ago';
  if (delta.inHours < 24) return '${delta.inHours}h ago';
  if (delta.inDays < 7) return '${delta.inDays}d ago';
  return '${(delta.inDays / 7).floor()}w ago';
}
