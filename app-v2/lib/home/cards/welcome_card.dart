import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/companion/companion_signals.dart';
import 'package:nooto_v2/home/cards/card_entrance.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/companion_stream_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// First card the user sees on Home after onboarding completes. Voice
/// grammar — no bordered container; renders as direct assistant text on the
/// screen. TTL is intentionally long; the card is dismissed once via "Got it"
/// and never re-emitted.
///
/// Generator: [welcomeCardFor]. Emits once per onboarding completion if not
/// already dismissed.
final class WelcomeCard extends CompanionCard {
  WelcomeCard({
    required this.preferredName,
    required this.generatedAt,
  });

  final String preferredName;
  @override
  final DateTime generatedAt;

  @override
  String get id => 'welcome:once';

  @override
  CardKind get kind => CardKind.welcome;

  @override
  int get priority => 1000;

  /// Welcome card stays around until explicitly dismissed. Generator suppresses
  /// re-emit once `home.actions.v1` has a dismiss row for this id.
  @override
  Duration get ttl => const Duration(days: 365);

  @override
  Map<String, dynamic> toJson() => {
        'kind': kind.code,
        'preferredName': preferredName,
        'generatedAt': generatedAt.toIso8601String(),
      };

  factory WelcomeCard.fromJson(Map<String, dynamic> json) {
    return WelcomeCard(
      preferredName: json['preferredName'] as String? ?? '',
      generatedAt: DateTime.parse(json['generatedAt'] as String),
    );
  }

  @override
  void onAction(BuildContext context, CardAction action) {
    if (action != CardAction.dismiss) return;
    context.read<CompanionStreamProvider>().recordAction(this, action);
  }

  @override
  Widget render(BuildContext context) => _WelcomeCardView(card: this);
}

/// Public generator. Returns null when there's no useful greeting to make
/// (no preferred name on file). Provider's dedup handles "already dismissed."
WelcomeCard? welcomeCardFor(CompanionSignals signals) {
  return WelcomeCard(
    preferredName: signals.preferredName ?? '',
    generatedAt: DateTime.now(),
  );
}

class _WelcomeCardView extends StatelessWidget {
  const _WelcomeCardView({required this.card});

  final WelcomeCard card;

  @override
  Widget build(BuildContext context) {
    final name = card.preferredName.trim();
    final greeting = name.isEmpty ? 'Welcome.' : 'Welcome, $name.';

    return CardEntrance(
      child: Semantics(
        label: '$greeting I will start by listening for the things you say '
            "you'll do. When you commit to something, it'll show up here so "
            "you don't have to remember it twice.",
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppStyles.spacingL,
            vertical: AppStyles.spacingM,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                greeting,
                style: brandEmphasis(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: AppStyles.spacingM),
              const Text(
                "I'll start by listening for the things you say you'll do. "
                "When you commit to something, it'll show up here — so you "
                "don't have to remember it twice.",
                style: TextStyle(
                  fontSize: 16,
                  color: AppColors.textSecondary,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: AppStyles.spacingM),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => card.onAction(context, CardAction.dismiss),
                  style: TextButton.styleFrom(
                    foregroundColor: AppColors.brandPrimary,
                    minimumSize: const Size(
                      AppStyles.touchTargetMinimum,
                      AppStyles.touchTargetMinimum,
                    ),
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppStyles.spacingL,
                    ),
                  ),
                  child: const Text(
                    'Got it',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
