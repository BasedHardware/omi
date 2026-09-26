import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_capturing/capture_state_header.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A conversation whose recording has ended and whose summary is being made.
///
/// Same header as the live and saved pages (circled back, the state as the title: Processing).
/// There is one view — the transcript or photos captured so far — because the summary does not
/// exist yet; the saved page adds its tabs once it does.
class ProcessingConversationPage extends StatelessWidget {
  final ServerConversation conversation;

  const ProcessingConversationPage({super.key, required this.conversation});

  @override
  Widget build(BuildContext context) {
    final hasContent = conversation.transcriptSegments.isNotEmpty || conversation.photos.isNotEmpty;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: const ConversationStateAppBar(
        state: CaptureDisplayState.processing,
        backKey: ValueKey('processing_conversation_back_button'),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const _ProcessingSteps(),
            const SizedBox(height: OmiSpacing.md),
            Expanded(
              child: hasContent
                  ? getTranscriptWidget(
                      false,
                      conversation.transcriptSegments,
                      conversation.photos,
                      null,
                      conversationId: conversation.id,
                      bottomMargin: OmiSpacing.xxl,
                    )
                  : OmiEmptyState(icon: Icons.hourglass_empty, title: context.l10n.noContentToDisplay),
            ),
          ],
        ),
      ),
    );
  }
}

/// v2 "Wrapping up": what is done (the transcript is saved) and what Omi is doing now.
class _ProcessingSteps extends StatelessWidget {
  const _ProcessingSteps();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // "Summarizing conversation…\nThis may take a few seconds": a title and its note.
    final summarizing = l10n.summarizingConversation.split('\n');
    Widget step({required Widget leading, required String title, String? note}) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 24, height: 24, child: Center(child: leading)),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: OmiType.headline),
                    if (note != null && note.trim().isNotEmpty)
                      Text(note.trim(), style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  ],
                ),
              ),
            ],
          ),
        );
    return Container(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.rowAll),
      child: Column(
        children: [
          step(
            leading: Icon(Icons.check_circle_rounded, size: 22, color: OmiColors.textPrimary),
            title: l10n.transcript,
          ),
          Divider(height: 0.5, thickness: 0.5, indent: OmiSpacing.md, color: OmiColors.border),
          step(
            leading: const OmiRingLogo(size: 18, mode: OmiRingMode.chase),
            title: summarizing.first,
            note: summarizing.length > 1 ? summarizing.sublist(1).join(' ') : null,
          ),
        ],
      ),
    );
  }
}
