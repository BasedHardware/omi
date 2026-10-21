import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/chat_apps_analytics.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What the WhatsApp waitlist sheet asked the page to do next.
enum WhatsAppWaitlistAction { useTelegram }

/// WhatsApp is not offered yet. "Notify Me" is remembered on this device and counted in the
/// chat-apps funnel; there is no waitlist API, so nobody is messaged from it.
Future<WhatsAppWaitlistAction?> showWhatsAppWaitlistSheet(BuildContext context, {required bool offerTelegram}) {
  return showOmiSheet<WhatsAppWaitlistAction>(
    context: context,
    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
    builder: (_) => WhatsAppWaitlistSheet(offerTelegram: offerTelegram),
  );
}

class WhatsAppWaitlistSheet extends StatelessWidget {
  const WhatsAppWaitlistSheet({super.key, required this.offerTelegram});

  /// Telegram is available and not yet connected.
  final bool offerTelegram;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<MessagingChannelsProvider>();
    final joined = provider.whatsAppWaitlisted;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Center(child: ChatAppLogo(ChatChannel.whatsapp, size: 56)),
          const SizedBox(height: OmiSpacing.md),
          ChatAppsSheetHeading(title: l10n.chatAppsWhatsAppTitle, message: l10n.chatAppsWhatsAppMessage),
          const SizedBox(height: OmiSpacing.xl),
          ChatAppsNote(title: l10n.chatAppsInTheMeantime, message: l10n.chatAppsWhatsAppMeantime),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const ValueKey('chat_apps_whatsapp_notify'),
            label: joined ? l10n.chatAppsOnTheList : l10n.chatAppsNotifyMe,
            icon: joined ? Icons.check_rounded : null,
            expand: true,
            onPressed: joined
                ? null
                : () async {
                    await provider.joinWhatsAppWaitlist();
                    ChatAppsAnalytics.waitlistJoined();
                    if (context.mounted) OmiFeedback.confirm(context, l10n.chatAppsWaitlistConfirmed);
                  },
          ),
          if (offerTelegram) ...[
            const SizedBox(height: OmiSpacing.xxs),
            OmiButton.tertiary(
              key: const ValueKey('chat_apps_whatsapp_use_telegram'),
              label: l10n.chatAppsUseTelegramForNow,
              expand: true,
              onPressed: () => Navigator.of(context).pop(WhatsAppWaitlistAction.useTelegram),
            ),
          ],
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}
