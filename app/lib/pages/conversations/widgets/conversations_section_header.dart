import 'package:flutter/material.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_provider.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcripts_page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

class ConversationsSectionHeader extends StatelessWidget {
  const ConversationsSectionHeader({
    super.key,
    required this.showDailySummaries,
    required this.hasOmiConversationState,
  });

  final bool showDailySummaries;
  final bool hasOmiConversationState;

  static bool shouldShow({
    required bool showDailySummaries,
    required bool hasOmiConversationState,
    required bool cloudflareEnabled,
  }) {
    return showDailySummaries || hasOmiConversationState || cloudflareEnabled;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CloudflareTranscriptProvider>(
      builder: (context, provider, _) {
        if (!shouldShow(
          showDailySummaries: showDailySummaries,
          hasOmiConversationState: hasOmiConversationState,
          cloudflareEnabled: provider.enabled,
        )) {
          return const SizedBox.shrink();
        }

        return Padding(
          padding: const EdgeInsets.only(left: 24, right: 16, top: 16, bottom: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(
                showDailySummaries ? context.l10n.dailyRecaps : context.l10n.conversations,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              if (!showDailySummaries && provider.enabled)
                IconButton(
                  key: const Key('cloudflare_transcripts_entry'),
                  tooltip: context.l10n.transcriptTab,
                  icon: const Icon(Icons.subject_outlined),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => const CloudflareTranscriptsPage()),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
