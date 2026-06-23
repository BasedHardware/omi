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

    // Merge conversations and recordings into one time-sorted list (newest first),
    // matching how conversations are ordered within a date.
    final entries = <({DateTime time, ServerConversation? convo, LocalRecording? rec})>[
      for (final c in conversations) (time: c.startedAt ?? c.createdAt, convo: c, rec: null),
      for (final r in recordings) (time: r.startedAt, convo: null, rec: r),
    ]..sort((a, b) => b.time.compareTo(a.time));

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DateListItem(date: date, isFirst: isFirst),
        ...entries.map((e) {
          if (e.convo != null) {
            return ConversationListItem(
              key: ValueKey(e.convo!.id),
              conversation: e.convo!,
              conversationIdx: conversations.indexOf(e.convo!),
              date: date,
            );
          }
          return RecordingListItem(key: ValueKey('rec_${e.rec!.id}'), recording: e.rec!);
        }),
        const SizedBox(height: 10),
      ],
    );
  }
}
