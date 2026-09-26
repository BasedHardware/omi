import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Ask before the first question (v2 Ask): the Omi mark, what you can ask and where answers come
/// from, then suggestions as chips. Starters stay editable in the composer; choosing one never
/// sends a message.
class ChatStarters extends StatelessWidget {
  final bool hasExistingData;
  final bool isConnected;
  final ValueChanged<String> onSelected;

  const ChatStarters({super.key, required this.hasExistingData, required this.isConnected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    if (!isConnected) {
      return Center(child: Text(context.l10n.noInternetConnection, textAlign: TextAlign.center));
    }
    final l10n = context.l10n;
    // Rev 3 Ask: with something heard, questions about it; before that, what Omi can do.
    final prompts = hasExistingData
        ? [('today', l10n.askStarterToday), ('people', l10n.askStarterPeople), ('open', l10n.askStarterOpen)]
        : [('capabilities', l10n.chatStarterPrompt('capabilities')), ('goal', l10n.chatStarterPrompt('goal'))];
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(OmiSpacing.xl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const OmiRingLogo(size: 56, mode: OmiRingMode.orbit, loops: 1),
              const SizedBox(height: 18),
              Semantics(
                header: true,
                child: Text(l10n.askEmptyTitle, textAlign: TextAlign.center, style: OmiType.serifTitle),
              ),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                l10n.askEmptySubtitle,
                textAlign: TextAlign.center,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              ),
              const SizedBox(height: OmiSpacing.xl),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: OmiSpacing.xs,
                runSpacing: OmiSpacing.xs,
                children: [
                  for (final (kind, prompt) in prompts)
                    _SuggestionChip(
                      key: ValueKey('chat_starter_$kind'),
                      label: prompt,
                      onTap: () => onSelected(prompt),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A question to start with (v2 Ask suggestions): an outlined 38 pt capsule.
class _SuggestionChip extends StatelessWidget {
  const _SuggestionChip({super.key, required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      onTap: onTap,
      child: OmiPressable(
        onTap: () {
          OmiHaptics.selection();
          onTap();
        },
        child: Container(
          constraints: const BoxConstraints(minHeight: 38),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 9),
          decoration: BoxDecoration(
            borderRadius: OmiRadius.pillAll,
            border: Border.all(color: OmiColors.textPrimary.withValues(alpha: 0.28), width: 0.5),
          ),
          child: Text(label, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
        ),
      ),
    );
  }
}
