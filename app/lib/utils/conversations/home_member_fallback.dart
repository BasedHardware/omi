import 'package:omi/backend/schema/conversation.dart';

/// Each server omission has an exact snapshot held by this client. Keep that
/// snapshot in the local source list so replacing an overlay cannot orphan it.
List<ServerConversation> retainSuppressedHomeMembers(
    List<ServerConversation> returned, Map<String, ServerConversation> held, Iterable<String> suppressedIds) {
  final present = returned.map((c) => c.id).toSet();
  return [
    ...returned,
    for (final id in suppressedIds)
      if (held[id] case final member? when present.add(id)) member,
  ];
}

/// Only acknowledge full, settled source snapshots that this client can restore.
Map<String, List<ServerConversation>> acknowledgeLoadedHomeMembers(
    Map<String, List<ServerConversation>> episodes, List<ServerConversation> source) {
  final loaded = {for (final c in source) c.id: c};
  return {
    for (final entry in episodes.entries)
      // A locked member locks the whole episode row. Keep the original source
      // payloads until that row offers access to every acknowledged member.
      if (!entry.value.any((m) => m.isLocked || loaded[m.id]?.isLocked == true))
        entry.key: [
          for (final member in entry.value)
            if (loaded[member.id] case final c?
                when c.status == ConversationStatus.completed &&
                    !c.isHiddenFromDefaultList &&
                    !c.isLocked &&
                    !c.processingDeferred &&
                    c.clientProcessing == null &&
                    !c.summaryRetryable &&
                    c.structured.title.trim().isNotEmpty)
              c,
        ],
  };
}

/// List reads omit transcripts. A title or summary is enough to keep a settled
/// row ordinary; only completed, otherwise empty captures await speech here.
bool awaitingHomeTranscript(ServerConversation c) =>
    c.status == ConversationStatus.completed &&
    !c.isHiddenFromDefaultList &&
    !c.isLocked &&
    !c.summaryRetryable &&
    !c.processingDeferred &&
    c.clientProcessing == null &&
    c.photos.isEmpty &&
    c.structured.title.trim().isEmpty &&
    c.structured.overview.trim().isEmpty &&
    !c.transcriptSegments.any((s) => s.text.trim().isNotEmpty);
