import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/activation/activation_flow.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// For people who skipped the first conversation in onboarding: a short welcome on Home that says
/// how Omi works. Gone once they have a conversation, or when they close it.
class OnboardingWelcomeCard extends StatefulWidget {
  const OnboardingWelcomeCard({super.key});

  @override
  State<OnboardingWelcomeCard> createState() => _OnboardingWelcomeCardState();
}

class _OnboardingWelcomeCardState extends State<OnboardingWelcomeCard> {
  late bool _show = SharedPreferencesUtil().getBool(ActivationFlow.welcomeCardKey);

  void _close() {
    OmiHaptics.selection();
    SharedPreferencesUtil().saveBool(ActivationFlow.welcomeCardKey, false);
    setState(() => _show = false);
  }

  @override
  Widget build(BuildContext context) {
    if (!_show) return const SizedBox.shrink();
    final hasConversations = context.select<ConversationProvider, bool>((p) => p.conversations.isNotEmpty);
    if (hasConversations) return const SizedBox.shrink();
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: Container(
        key: const Key('onboarding_welcome_card'),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.xs, OmiSpacing.lg),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.xs),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('👋  ${l10n.onboardingWelcomeCardTitle}', style: OmiType.headline),
                    const SizedBox(height: OmiSpacing.xs),
                    Text(
                      l10n.onboardingWelcomeCardBody,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                    ),
                  ],
                ),
              ),
            ),
            OmiIconButton(
              key: const Key('onboarding_welcome_card_close'),
              icon: const Icon(Icons.close_rounded, size: 20),
              label: l10n.close,
              onPressed: _close,
            ),
          ],
        ),
      ),
    );
  }
}
