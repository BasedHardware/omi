import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

bool ownsHomeLiveWindow(ServerConversation window, CaptureProvider capture) {
  if (EpisodePresentation.streamingSource(capture) == null) return false;
  // topConversationId comes from the account-wide list. Only IDs from this capture prove ownership.
  final recordings = window.v3?.recordingIds ?? const <String>[];
  return recordings.contains(capture.activeRecordingId) ||
      recordings.contains(capture.verifiedLiveServerRecordingId) ||
      LiveConversationEndButton.ownsCapture(window, capture.locallyReceivedSegmentIds);
}

class HomeLiveFinishButton extends StatelessWidget {
  const HomeLiveFinishButton({super.key, required this.onPressed});

  final Future<void> Function() onPressed;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.4),
      child: OmiButton.secondary(
        key: const Key('home_live_finish'),
        label: context.l10n.finish,
        onPressed: onPressed,
        size: OmiButtonSize.compact,
        pill: true,
      ),
    );
  }
}
