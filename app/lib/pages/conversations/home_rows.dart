import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';

/// A display row only: neither episodes nor conversations are mutated or persisted.
class HomeRow {
  const HomeRow(this.conversation, {this.episode});
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
    List<ServerConversation> knownConversations = const []}) {
  if (!enabled) return [for (final c in conversations) HomeRow(c)];
  final byId = {for (final c in conversations) c.id: c, for (final c in knownConversations) c.id: c};
  final hidden = {...liveConversationIds};
  final rows = <HomeRow>[];
  final singleIds = <String>{};
  for (final episode in episodes) {
    // Live capture retains its existing row and ownership rules.
    if (episode.live) continue;
    final metadata = {for (final c in episode.members) c.id: c};
    final members = <ServerConversation>[];
    for (final id in episode.conversationIds.toSet()) {
      final member = byId[id] ?? metadata[id];
      hidden.add(id);
      if (member != null && !member.discarded && !member.deleted && !deletedIds.contains(id)) members.add(member);
    }
    if (members.isEmpty) continue;
    if (members.length == 1) {
      if (singleIds.add(members.single.id)) rows.add(HomeRow(members.single));
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
        episode: episode.copyWith(members: members)));
  }
  rows.addAll([
    for (final c in conversations)
      if (!hidden.contains(c.id) && !deletedIds.contains(c.id)) HomeRow(c)
  ]);
  rows.sort((a, b) => b.startedAt.compareTo(a.startedAt));
  return rows;
}
