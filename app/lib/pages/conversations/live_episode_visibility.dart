import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/services/experiments/client_refactor_flags.dart';

/// A live episode replaces unfinished conversations. Finished rows,
/// including highlights, become available without waiting for the episode to close.
Set<String> hiddenLiveConversations(Set<String> episodeIds, Iterable<ServerConversation> conversations,
    {required bool serving}) {
  final inProgress = conversations
      .where((c) => c.status != ConversationStatus.completed && c.status != ConversationStatus.failed)
      .map((c) => c.id)
      .toSet();
  final hidden = episodeIds.intersection(inProgress);
  ClientRefactorFlags.compare('home_visibility', hidden.length == episodeIds.length);
  // refactor: superseded by live_episode_visibility when clients_refactor=serve
  return serving ? hidden : episodeIds;
}

/// Conversations offline sync is still adding audio to, with how much: the server's pending sync
/// jobs that name their target conversation.
Map<String, int> fillingSeconds(List<PendingWorkItem> pending) {
  final filling = <String, int>{};
  for (final item in pending) {
    if (item.kind != 'sync_job' || item.state == 'summarizing' || item.conversationIds.length != 1) continue;
    final seconds = item.durationSeconds ?? 0;
    if (seconds <= 0) continue;
    filling.update(item.conversationIds.single, (v) => v + seconds, ifAbsent: () => seconds);
  }
  return filling;
}
