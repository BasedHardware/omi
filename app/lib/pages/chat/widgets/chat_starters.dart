import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Starters stay editable in the composer; choosing one never sends a message.
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
    final prompts = hasExistingData ? ['activity', 'improve'] : ['capabilities', 'goal'];
    return Center(
        child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.auto_awesome_outlined, size: 28, color: OmiColors.textSecondary),
              const SizedBox(height: 16),
              Text(context.l10n.askOmi, textAlign: TextAlign.center, style: OmiType.title3),
              const SizedBox(height: 24),
              for (final kind in prompts)
                Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: OutlinedButton(
                      key: ValueKey('chat_starter_$kind'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        backgroundColor: Colors.white.withValues(alpha: 0.04),
                        minimumSize: const Size.fromHeight(56),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                        side: const BorderSide(color: OmiColors.border),
                        shape: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
                      ),
                      onPressed: () => onSelected(context.l10n.chatStarterPrompt(kind)),
                      child: Row(children: [
                        Expanded(child: Text(context.l10n.chatStarterPrompt(kind))),
                        const SizedBox(width: 12),
                        const Icon(Icons.north_west, size: 18, color: OmiColors.textTertiary),
                      ]),
                    )),
            ],
          )),
    ));
  }
}
