import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/local_recording.dart';
import 'conversation_list_item.dart';
import 'date_list_item.dart';
import 'recording_list_item.dart';

class ConversationsGroupWidget extends StatelessWidget {
  final List<ServerConversation> conversations;

  /// Unsynced local recordings (batch/offline mode) for this date, interleaved with
  /// conversations by time. They have no title/icon yet — see [RecordingListItem].
  final List<LocalRecording> recordings;
  final DateTime date;
  final bool isFirst;
  const ConversationsGroupWidget({
    super.key,
    required this.conversations,
    this.recordings = const [],
    required this.date,
    required this.isFirst,
  });

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty && recordings.isEmpty) {
      return const SizedBox.shrink();
    }

    final entries = buildConversationGroupEntries(conversations: conversations, recordings: recordings);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DateListItem(date: date, isFirst: isFirst),
        ...entries.map((e) {
          if (e.conversation != null) {
            return ConversationListItem(
              key: ValueKey(e.conversation!.id),
              conversation: e.conversation!,
              conversationIdx: conversations.indexOf(e.conversation!),
              date: date,
            );
          }
          return RecordingListItem(key: ValueKey('rec_${e.recording!.id}'), recording: e.recording!);
        }),
        const SizedBox(height: 10),
      ],
    );
  }
}

typedef ConversationGroupEntry = ({DateTime time, ServerConversation? conversation, LocalRecording? recording});

/// Merge conversations and local recordings into the time-sorted order used by
/// the conversations page. The page consumes these lightweight descriptors in
/// a sliver builder so only visible rows become widgets.
List<ConversationGroupEntry> buildConversationGroupEntries({
  required List<ServerConversation> conversations,
  required List<LocalRecording> recordings,
}) {
  return <ConversationGroupEntry>[
    for (final conversation in conversations)
      (time: conversation.startedAt ?? conversation.createdAt, conversation: conversation, recording: null),
    for (final recording in recordings) (time: recording.startedAt, conversation: null, recording: recording),
  ]..sort((a, b) => b.time.compareTo(a.time));
}
