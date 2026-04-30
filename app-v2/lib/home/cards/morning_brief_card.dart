import 'package:flutter/material.dart';

import 'package:nooto_v2/home/cards/card_entrance.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Synthesized daily brief, voice grammar (no chrome). Sits between the
/// welcome card (priority 1000) and the Today surface card (priority 500),
/// so on a typical Home open the visual flow is:
///
///   ┌ Welcome, Matheus.       (voice, sans-serif bold greeting)
///   ┌ Yesterday you said you'd email John…    (this card, voice)
///   └ Today: ⦁ Email John ⦁ Soccer 8pm        (Today surface card)
///
/// Cached in `home.brief.v1` keyed by local-tz date so a second open the
/// same day doesn't burn another LLM call.
final class MorningBriefCard extends CompanionCard {
  MorningBriefCard({
    required this.dateKey,
    required this.greeting,
    required this.body,
    required this.generatedAt,
  });

  /// Local-timezone YYYY-MM-DD. Same key the cache uses.
  final String dateKey;

  /// One-line opener like "Good morning, Matheus." The card renderer pairs
  /// it with the body. Empty string suppresses the greeting line.
  final String greeting;

  /// Synthesized brief paragraph(s) from the LLM proxy.
  final String body;

  @override
  final DateTime generatedAt;

  @override
  String get id => '$_idPrefix$dateKey';

  @override
  CardKind get kind => CardKind.brief;

  @override
  int get priority => 750;

  @override
  Duration get ttl => const Duration(hours: 24);

  @override
  Map<String, dynamic> toJson() => {
        'kind': kind.code,
        'dateKey': dateKey,
        'greeting': greeting,
        'body': body,
        'generatedAt': generatedAt.toIso8601String(),
      };

  factory MorningBriefCard.fromJson(Map<String, dynamic> json) {
    return MorningBriefCard(
      dateKey: json['dateKey'] as String,
      greeting: json['greeting'] as String? ?? '',
      body: json['body'] as String? ?? '',
      generatedAt: DateTime.parse(json['generatedAt'] as String),
    );
  }

  @override
  void onAction(BuildContext context, CardAction action) {
    // Brief is read-only — no inline actions. Tapping does nothing for now;
    // a later pass could open a "remix" / regenerate flow.
  }

  @override
  Widget render(BuildContext context) => _MorningBriefView(card: this);

  static const String _idPrefix = 'brief:';
}

class _MorningBriefView extends StatelessWidget {
  const _MorningBriefView({required this.card});

  final MorningBriefCard card;

  @override
  Widget build(BuildContext context) {
    final hasGreeting = card.greeting.trim().isNotEmpty;
    return CardEntrance(
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppStyles.spacingL,
          vertical: AppStyles.spacingM,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (hasGreeting) ...[
              Text(
                card.greeting,
                style: brandEmphasis(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: AppStyles.spacingM),
            ],
            Text(
              card.body,
              style: const TextStyle(
                fontSize: 16,
                color: AppColors.textSecondary,
                height: 1.45,
              ),
            ),
            const SizedBox(height: AppStyles.spacingS),
            Text(
              _synthesizedAgo(card.generatedAt),
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textTertiary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Closes the "is this fresh?" loop. Brief is cached for 24h, so without
  /// this label a stale brief reads as live.
  String _synthesizedAgo(DateTime when) {
    final delta = DateTime.now().difference(when);
    if (delta.inMinutes < 2) return 'synthesized just now';
    if (delta.inMinutes < 60) return 'synthesized ${delta.inMinutes}m ago';
    if (delta.inHours < 6) return 'synthesized ${delta.inHours}h ago';
    final hour = when.hour;
    if (hour < 11) return 'synthesized this morning';
    if (hour < 17) return 'synthesized this afternoon';
    return 'synthesized this evening';
  }
}
