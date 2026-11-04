import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/utils/conversations/home_member_fallback.dart';

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

/// After an outage deadline, keep the grouping already painted until a refresh
/// boundary. Content remains current; late membership cannot absorb visible rows
/// or move an existing episode to another day. Source rows remain independently
/// available, including members restored by the list acknowledgement adapter.
class HomeEpisodeLayout {
  HomeEpisodeLayout(List<Episode> episodes) : _episodes = List.unmodifiable(episodes);

  final List<Episode> _episodes;

  List<Episode> apply(List<Episode> latest) {
    final byId = {for (final episode in latest) episode.id: episode};
    return [
      for (final previous in _episodes) _update(previous, byId[previous.id] ?? previous),
    ];
  }

  Episode _update(Episode previous, Episode latest) {
    final members = {for (final member in latest.members) member.id: member};
    return latest.copyWith(
      live: previous.live,
      startedAt: previous.startedAt,
      conversationIds: previous.conversationIds,
      members: [for (final member in previous.members) members[member.id] ?? member],
    );
  }
}

List<HomeRow> buildHomeRows(List<ServerConversation> conversations, List<Episode> episodes,
    {required bool enabled,
    Set<String> liveConversationIds = const {},
    Set<String> deletedIds = const {},
    List<ServerConversation> knownConversations = const [],
    List<ServerConversation> processingConversations = const [],
    String? finishingTitle,
    String? processingTitle,
    bool groupAwaitingTranscript = false,
    DateTime? now}) {
  if (!enabled && !groupAwaitingTranscript) return [for (final c in conversations) HomeRow(c)];
  final byId = {for (final c in conversations) c.id: c, for (final c in knownConversations) c.id: c};
  final hidden = {...liveConversationIds};
  final rows = <HomeRow>[];
  final singleIds = <String>{};
  for (final episode in enabled ? episodes : <Episode>[]) {
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
          finishedAt: episode.lastActivityAt,
          structured: retainedIds.length > 1
              ? Structured(finishingTitle ?? '', '', emoji: pending.first.structured.emoji)
              : pending.first.structured,
        ),
        episodeConversationIds: episode.conversationIds.toSet(),
        episode: episode,
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
    if (!episode.composed && members.any(awaitingHomeTranscript)) {
      rows.add(
          _processingRun(members, (members.length > 1 ? finishingTitle : processingTitle) ?? '', episode: episode));
      continue;
    }
    if (members.length == 1) {
      if (singleIds.add(members.single.id)) {
        rows.add(HomeRow(members.single, episodeConversationIds: episode.conversationIds.toSet()));
      }
      continue;
    }
    final primary = members.first;
    if (!episode.composed && episode.awaitingSummary(now ?? DateTime.now())) {
      rows.add(HomeRow(
        ServerConversation(
          id: 'episode:${episode.id}',
          createdAt: episode.startedAt,
          startedAt: episode.startedAt,
          finishedAt: episode.lastActivityAt,
          structured: Structured(finishingTitle ?? '', '', emoji: primary.structured.emoji),
        ),
        episodeConversationIds: episode.conversationIds.toSet(),
        episode: episode.copyWith(members: members),
        isProcessing: true,
      ));
      continue;
    }
    // A summary that never landed keeps its one row, and the page reads the running notes.
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
  if (!groupAwaitingTranscript) return rows;
  final grouped = <HomeRow>[];
  var run = <ServerConversation>[];
  void flush() {
    if (run.isNotEmpty) grouped.add(_processingRun(run, processingTitle ?? ''));
    run = [];
  }

  for (final row in rows) {
    final c = row.conversation;
    final contiguous = run.isEmpty ||
        (run.last.startedAt ?? run.last.createdAt).difference(c.finishedAt ?? c.startedAt ?? c.createdAt) <=
            const Duration(minutes: 2);
    if (row.episode == null && awaitingHomeTranscript(c)) {
      if (!contiguous) flush();
      run.add(c);
    } else {
      flush();
      grouped.add(row);
    }
  }
  flush();
  return grouped;
}

HomeRow _processingRun(List<ServerConversation> members, String title, {Episode? episode}) {
  final start = members.map((c) => c.startedAt ?? c.createdAt).reduce((a, b) => a.isBefore(b) ? a : b);
  final end = members.map((c) => c.finishedAt ?? c.startedAt ?? c.createdAt).reduce((a, b) => a.isAfter(b) ? a : b);
  final ids = members.map((c) => c.id).toSet();
  final parent = episode?.copyWith(members: members) ??
      Episode(
        id: '',
        live: false,
        startedAt: start,
        lastActivityAt: end,
        conversationIds: ids.toList(),
        members: members,
        title: title,
      );
  return HomeRow(
      ServerConversation(
        id: episode == null ? 'processing-run:${members.last.id}' : 'episode:${episode.id}',
        createdAt: start,
        startedAt: start,
        finishedAt: end,
        structured: Structured(title, ''),
      ),
      episode: parent,
      episodeConversationIds: episode?.conversationIds.toSet() ?? ids,
      isProcessing: true);
}
