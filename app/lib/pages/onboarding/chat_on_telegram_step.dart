import 'package:flutter/material.dart';

import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/telegram_connect_sheet.dart';
import 'package:omi/services/experiments/chat_apps_gate.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Optional final onboarding step: invite the reader to reach Omi from Telegram. Connecting (or
/// tapping Not Now) calls [onContinue] so the wrapper can finish onboarding. Only reached when the
/// Telegram channel is actually available; it never blocks completion.
class OnboardingChatOnTelegramStep extends StatelessWidget {
  final VoidCallback onContinue;

  const OnboardingChatOnTelegramStep({super.key, required this.onContinue});

  Future<void> _connect(BuildContext context) async {
    OmiHaptics.selection();
    // The connect sheet instruments connectStarted/connected itself — don't double-count here.
    final link = await showTelegramConnectSheet(context);
    // Advance only once a link exists; a dismissed sheet leaves the reader here to retry.
    if (link != null && context.mounted) onContinue();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: OmiColors.surface0,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.md, OmiSpacing.xl, OmiSpacing.xl),
          child: Column(
            children: [
              const Spacer(),
              const ChatAppLogo(ChatChannel.telegram, size: 72),
              const SizedBox(height: OmiSpacing.lg),
              Semantics(
                header: true,
                child: Text(
                  context.l10n.onboardingChatOnTelegramTitle,
                  textAlign: TextAlign.center,
                  style: OmiType.title1.copyWith(height: 1.2),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                context.l10n.onboardingChatOnTelegramBody,
                textAlign: TextAlign.center,
                style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4),
              ),
              const Spacer(),
              OmiButton(
                label: context.l10n.chatAppsConnectTelegramTitle,
                expand: true,
                onPressed: () => _connect(context),
              ),
              const SizedBox(height: OmiSpacing.md),
              OmiButton(
                variant: OmiButtonVariant.tertiary,
                label: context.l10n.maybeLater,
                expand: true,
                onPressed: () {
                  OmiHaptics.selection();
                  onContinue();
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}
