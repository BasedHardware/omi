import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';

/// A display row only: neither episodes nor conversations are mutated or persisted.
class HomeRow {
  const HomeRow(this.conversation, {this.episode, this.episodeConversationIds = const {}, this.isProcessing = false});
  final bool isProcessing;
  final Set<String> episodeConversationIds;
  final ServerConversation conversation;
  final Episode? episode;
  DateTime get startedAt => conversation.startedAt ?? conversation.createdAt;
  DateTime get day {
    final local = startedAt.toLocal();
    return DateTime(local.year, local.month, local.day);
  }
}

List<HomeRow> buildHomeRows(List<ServerConversation> conversations, List<Episode> episodes,
    {required bool enabled,
    Set<String> liveConversationIds = const {},
    Set<String> deletedIds = const {},
    List<ServerConversation> knownConversations = const [],
    List<ServerConversation> processingConversations = const []}) {
  if (!enabled) return [for (final c in conversations) HomeRow(c)];
  final byId = {for (final c in conversations) c.id: c, for (final c in knownConversations) c.id: c};
  final hidden = {...liveConversationIds};
  final rows = <HomeRow>[];
  final singleIds = <String>{};
  for (final episode in episodes) {
    final metadata = {for (final c in episode.members) c.id: c};
    // Full membership includes discarded members for Delete. Only retained
    // members may keep the episode's display row in processing.
    final retainedIds = metadata.isEmpty ? episode.conversationIds.toSet() : metadata.keys.toSet();
    final pending = processingConversations
        .where((c) => retainedIds.contains(c.id) && !c.discarded && !c.deleted && !deletedIds.contains(c.id))
        .toList();
    // A closing episode may still be live in the last server snapshot. The
    // streaming capture owns its row until it stops; then processing owns it.
    if (episode.live && (pending.isEmpty || episode.conversationIds.any(liveConversationIds.contains))) continue;
    final members = <ServerConversation>[];
    hidden.addAll(episode.conversationIds);
    if (pending.isNotEmpty) {
      rows.add(HomeRow(
        ServerConversation(
          id: 'episode:${episode.id}',
          createdAt: episode.startedAt,
          startedAt: episode.startedAt,
          structured: pending.first.structured,
        ),
        episodeConversationIds: episode.conversationIds.toSet(),
        isProcessing: true,
      ));
      continue;
    }
    // Server metadata is authoritative about retained membership. Full IDs also
    // include discarded members for Delete and must not resurrect stale local rows.
    for (final id in retainedIds) {
      final member = byId[id] ?? metadata[id];
      if (member != null && !member.discarded && !member.deleted && !deletedIds.contains(id)) members.add(member);
    }
    if (members.isEmpty) continue;
    if (members.length == 1) {
      if (singleIds.add(members.single.id)) {
        rows.add(HomeRow(members.single, episodeConversationIds: episode.conversationIds.toSet()));
      }
      continue;
    }
    final primary = members.first;
    final end = episode.lastActivityAt;
    // The adapter gives the existing row widget its exact typography, emoji tile and spacing.
    // It is never passed to a conversation mutation or detail API.
    rows.add(HomeRow(
        ServerConversation(
          id: 'episode:${episode.id}',
          isLocked: members.any((m) => m.isLocked),
          createdAt: episode.startedAt,
          startedAt: episode.startedAt,
          finishedAt: end,
          structured: Structured(episode.title.trim().isEmpty ? primary.structured.title : episode.title, '',
              emoji: episode.emoji.trim().isEmpty ? primary.structured.emoji : episode.emoji),
        ),
        episodeConversationIds: episode.conversationIds.toSet(),
        episode: episode.copyWith(members: members)));
  }
  rows.addAll([
    for (final c in conversations)
      if (!hidden.contains(c.id) && !deletedIds.contains(c.id)) HomeRow(c)
  ]);
  rows.sort((a, b) => b.startedAt.compareTo(a.startedAt));
  return rows;
}
