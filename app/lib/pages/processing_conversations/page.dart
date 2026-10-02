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
    );
  }
}
