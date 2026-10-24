import 'package:omi/backend/schema/pending_work.dart';

/// A live episode replaces its member conversations on Home: live splits, short
/// fragments, parallel and offline-sync captures, finished rows and highlights
/// all fold under the one live row, reachable inside the live episode page
/// (Moments, members). When the episode closes, the members return as ordinary
/// rows beside it — nothing here hides them then.
Set<String> hiddenLiveConversations(Set<String> episodeIds) => episodeIds;

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
