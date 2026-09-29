import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The empty chat: a greeting in the upper third and a row of starters just above the composer.
/// Starters stay editable in the composer; choosing one never sends a message.
class ChatStarters extends StatelessWidget {
  final bool hasExistingData;
  final bool isConnected;
  final ValueChanged<String> onSelected;

  /// Overrides the signed-in given name (tests and the visual audit).
  final String? givenName;

  const ChatStarters({
    super.key,
    required this.hasExistingData,
    required this.isConnected,
    required this.onSelected,
    this.givenName,
  });

  @override
  Widget build(BuildContext context) {
    final name = (givenName ?? SharedPreferencesUtil().givenName).trim();
    final l10n = context.l10n;
    final prompts = hasExistingData ? ['activity', 'improve'] : ['capabilities', 'goal'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Spacer(flex: 2),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
          child: TweenAnimationBuilder<double>(
            // The greeting settles in as the sheet lands.
            tween: Tween(begin: 0, end: 1),
            duration: const Duration(milliseconds: 520),
            curve: Curves.easeOutCubic,
            builder: (context, t, child) => Opacity(
              opacity: t,
              child: Transform.translate(offset: Offset(0, 8 * (1 - t)), child: child),
            ),
            child: Text(
              name.isEmpty ? l10n.askAnything : l10n.chatGreeting(name),
              key: const ValueKey('chat_greeting'),
              textAlign: TextAlign.center,
              style: OmiType.title2.copyWith(fontWeight: FontWeight.w500, letterSpacing: -0.3),
            ),
          ),
        ),
        if (!isConnected)
          Padding(
            padding: const EdgeInsets.only(top: OmiSpacing.sm),
            child: Text(
              l10n.noInternetConnection,
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
            ),
          ),
        const Spacer(flex: 3),
        if (isConnected)
          SizedBox(
            height: kOmiMinTapTarget,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
              itemCount: prompts.length,
              separatorBuilder: (_, __) => const SizedBox(width: OmiSpacing.xs),
              itemBuilder: (context, index) {
                final kind = prompts[index];
                final prompt = l10n.chatStarterPrompt(kind);
                return Center(
                  child: Semantics(
                    button: true,
                    child: GestureDetector(
                      key: ValueKey('chat_starter_$kind'),
                      behavior: HitTestBehavior.opaque,
                      onTap: () => onSelected(prompt),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                        decoration: BoxDecoration(
                          color: OmiColors.surface1,
                          borderRadius: OmiRadius.pillAll,
                          border: Border.all(color: OmiColors.border),
                        ),
                        child: Text(prompt, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        const SizedBox(height: OmiSpacing.xs),
      ],
    );
  }
}
