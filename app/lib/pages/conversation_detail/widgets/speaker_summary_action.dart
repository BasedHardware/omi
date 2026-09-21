import 'package:flutter/material.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// An opt-in action after a saved attribution change, not a staleness claim.
class SpeakerSummaryAction extends StatelessWidget {
  const SpeakerSummaryAction({super.key, required this.provider});
  final ConversationDetailProvider provider;
  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: provider,
        builder: (context, _) => !provider.offerSpeakerSummaryRefresh
            ? const SizedBox.shrink()
            : Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  key: const ValueKey('speaker-summary-refresh'),
                  onPressed: provider.loadingReprocessConversation ? null : () => provider.reprocessConversation(),
                  icon: provider.loadingReprocessConversation
                      ? const SizedBox(
                          width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.refresh, color: Colors.white70),
                  label: Text(context.l10n.updateSummaryWithNewNames, style: const TextStyle(color: Colors.white)),
                )),
      );
}
