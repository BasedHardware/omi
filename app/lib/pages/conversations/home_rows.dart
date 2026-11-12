import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/utils/conversations/home_member_fallback.dart';

/// What a Home row that is not finished yet is waiting on, least advanced first.
/// A run of such rows shows its least advanced step. Confirmed placement keeps
/// failures only in Activity; rollback retains the previous terminal Home rows.
enum HomeStep { transcribing, writingNotes, failed }

/// A display row only: neither episodes nor conversations are mutated or persisted.
class HomeRow {
  const HomeRow(this.conversation,
      {this.episode, this.episodeConversationIds = const {}, this.isProcessing = false, this.step, this.count = 1});
  final bool isProcessing;

  /// Set on every processing row; null on finished rows.
  final HomeStep? step;

  /// How many recordings this row stands for.
  final int count;

  HomeRow withStep(HomeStep step) => HomeRow(conversation,
      episode: episode, episodeConversationIds: episodeConversationIds, isProcessing: true, step: step, count: count);
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
  HomeEpisodeLayout(List<Episode> episodes) : _episodes = {for (final episode in episodes) episode.id: episode};

  final Map<String, Episode> _episodes;

  List<Episode> apply(List<Episode> latest, {required Set<String> standaloneIds}) {
    final occupied = {
      ...standaloneIds,
      for (final episode in _episodes.values) ..._memberIds(episode),
    };
    for (final episode in latest) {
      if (_episodes.containsKey(episode.id)) continue;
      final ids = _memberIds(episode);
      if (ids.isEmpty || ids.any(occupied.contains)) continue;
      // A new recording can appear immediately without absorbing a painted row.
      // Retain its first layout too, so a later membership change cannot remove
      // it or absorb an older standalone row on a subsequent notification.
      _episodes[episode.id] = episode;
      occupied.addAll(ids);
    }
    final byId = {for (final episode in latest) episode.id: episode};
    final projection = [
      for (final previous in _episodes.values) _update(previous, byId[previous.id] ?? previous),
    ];
    // An omitted episode keeps its last content/status, not its outage-era draft.
    for (final episode in projection) {
      _episodes[episode.id] = episode;
    }
    return projection;
  }

  Set<String> _memberIds(Episode episode) =>
      {...episode.conversationIds, for (final member in episode.members) member.id};

  Episode _update(Episode previous, Episode latest) {
    final members = {for (final member in latest.members) member.id: member};
    return latest.copyWith(
      startedAt: previous.startedAt,
      conversationIds: previous.conversationIds,
      members: [for (final member in previous.members) members[member.id] ?? member],
    );
  }
}

/// Failed status and the server's failed projection both belong to Activity.
bool isFailedHomeConversation(ServerConversation c) =>
    c.status == ConversationStatus.failed || homeStepOf(c) == HomeStep.failed;

List<HomeRow> buildHomeRows(List<ServerConversation> conversations, List<Episode> episodes,
    {required bool enabled,
    Set<String> liveConversationIds = const {},
    String? liveEpisodeId,
    Set<String> deletedIds = const {},
    List<ServerConversation> knownConversations = const [],
    List<ServerConversation> processingConversations = const [],
    String? finishingTitle,
    String? processingTitle,
    bool groupAwaitingTranscript = false,
    bool processingTodayOnly = false,
    bool activityOnlyFailures = false,
    DateTime? now}) {
  if (!enabled && !groupAwaitingTranscript) {
    return [
      for (final c in conversations)
        if (!activityOnlyFailures || !isFailedHomeConversation(c)) HomeRow(c)
    ];
  }
  final failedIds = <String>{
    if (activityOnlyFailures)
      for (final c in [
        ...conversations,
        ...knownConversations,
        ...processingConversations,
        for (final e in episodes) ...e.members
      ])
        if (isFailedHomeConversation(c)) c.id,
  };
  final byId = {for (final c in conversations) c.id: c, for (final c in knownConversations) c.id: c};
  final listeningOwnedIds = {...liveConversationIds};
  final hidden = {...liveConversationIds, ...failedIds};
  final rows = <HomeRow>[];
  final singleIds = <String>{};
  final failures = <String, ServerConversation>{
    for (final c in conversations)
      if (!activityOnlyFailures && c.homeStep == 'failed' && (c.episodeId == null || c.episodeId!.isEmpty)) c.id: c,
  };
  // A conversation's episode_id arrives with the list row, often before the
  // episode fetch. Reconstruct its owner immediately instead of flashing a
  // standalone row and later moving it into the episode.
  final owners = <String, Episode>{
    if (enabled)
      for (final e in episodes) e.id: e
  };
  for (final c in byId.values) {
    final id = c.episodeId;
    if (id == null || id.isEmpty) continue;
    final previous = owners[id];
    owners[id] = previous == null
        ? Episode(
            id: id,
            live: false,
            startedAt: c.startedAt ?? c.createdAt,
            lastActivityAt: c.finishedAt ?? c.createdAt,
            conversationIds: [c.id],
            members: [c])
        : previous.copyWith(conversationIds: {...previous.conversationIds, c.id}.toList(), members: [
            for (final m in previous.members)
              if (m.id != c.id) m,
            c
          ]);
  }
  for (final episode in owners.values) {
    final metadata = {for (final c in episode.members) c.id: c};
    // Full membership includes discarded members for Delete. Only retained
    // members may keep the episode's display row in processing.
    final retainedIds = metadata.isEmpty ? episode.conversationIds.toSet() : metadata.keys.toSet();
    for (final id in retainedIds) {
      final member = byId[id] ?? metadata[id];
      if (!activityOnlyFailures &&
          member?.homeStep == 'failed' &&
          (member?.episodeId == null || member!.episodeId!.isEmpty)) {
        failures[id] = member!;
      }
    }
    final pending = processingConversations
        .where((c) => retainedIds.contains(c.id) && !c.discarded && !c.deleted && !deletedIds.contains(c.id))
        .where((c) => !failedIds.contains(c.id) && !_serverFinished(c))
        .toList();
    final listeningOwns =
        episode.live && (episode.id == liveEpisodeId || episode.conversationIds.any(liveConversationIds.contains));
    // Only an actual Listening row replaces these members. A stale live
    // snapshot with no capture must keep its completed recordings visible.
    if (listeningOwns) {
      listeningOwnedIds.addAll({...episode.conversationIds, ...retainedIds});
      hidden.addAll(episode.conversationIds);
    }
    // A closing episode may still be live in the last server snapshot. The
    // streaming capture owns its row until it stops; then processing owns it.
    if (listeningOwns) {
      continue;
    }
    final members = <ServerConversation>[];
    hidden.addAll(episode.conversationIds);
    // Notes that already landed stay on Home: a member still processing (a late joiner, or a
    // stale local processing entry) never turns a composed episode back into "Finishing up…".
    // The episode page applies the same rule, so the row and its page agree.
    if (pending.isNotEmpty && !episode.composed) {
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
        step: _leastAdvanced(pending.map(_episodeStepOf)),
        count: retainedIds.length,
      ));
      continue;
    }
    // Server metadata is authoritative about retained membership. Full IDs also
    // include discarded members for Delete and must not resurrect stale local rows.
    for (final id in retainedIds) {
      final member = byId[id] ?? metadata[id];
      if (member != null &&
          !member.discarded &&
          !member.deleted &&
          !deletedIds.contains(id) &&
          !failedIds.contains(id) &&
          (member.homeStep != 'failed' || member.episodeId == episode.id) &&
          (member.episodeId == null || member.episodeId!.isEmpty || member.episodeId == episode.id)) {
        members.add(member);
      }
    }
    if (members.isEmpty) continue;
    // Noise and legacy failures have no episode row. Projected failures keep their explicit owner.
    if (groupAwaitingTranscript &&
        members.every((m) => isHomeNoise(m) || (homeStepOf(m) == HomeStep.failed && m.episodeId != episode.id))) {
      continue;
    }
    if (!episode.composed && members.any(awaitingHomeTranscript)) {
      rows.add(_processingRun(members, (members.length > 1 ? finishingTitle : processingTitle) ?? '',
          episode: episode, step: HomeStep.transcribing));
      continue;
    }
    if (members.length == 1) {
      if (singleIds.add(members.single.id)) {
        rows.add(HomeRow(members.single,
            episode: members.single.episodeId == episode.id ? episode.copyWith(members: members) : null,
            episodeConversationIds: episode.conversationIds.toSet()));
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
        step: HomeStep.writingNotes,
        count: members.length,
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
      if (!hidden.contains(c.id) && !failures.containsKey(c.id) && !deletedIds.contains(c.id)) HomeRow(c),
    for (final c in failures.values)
      // Failures escape closed episode grouping, but Listening still owns its members.
      if (!listeningOwnedIds.contains(c.id) && !c.deleted && !c.discarded && !deletedIds.contains(c.id)) HomeRow(c)
  ]);
  rows.sort((a, b) => b.startedAt.compareTo(a.startedAt));
  if (!groupAwaitingTranscript) return rows;
  // Noise (no speech worth a row) never shows on Home; search and direct links still reach it.
  // Legacy summary failures belong to Activity; age-projected failures have no ledger item.
  rows.removeWhere((row) =>
      row.episode == null &&
      (isHomeNoise(row.conversation) ||
          (homeStepOf(row.conversation) == HomeStep.failed && row.conversation.homeStep != 'failed')));
  final folded = foldProcessingRuns(rows, processingTitle: processingTitle ?? '');
  if (processingTodayOnly) {
    final today = localHomeDay(now ?? DateTime.now());
    folded.removeWhere((row) => row.isProcessing && row.day != today);
  }
  return folded;
}

DateTime localHomeDay(DateTime at) {
  final local = at.toLocal();
  return DateTime(local.year, local.month, local.day);
}

/// Home shows finished conversations, and every unbroken run of unfinished ones as a
/// single Processing row (one per day). A run's step is its least advanced member's.
/// Explicit failures break a run and remain openable terminal rows.
/// Every visible member stays reachable
/// from the run's page; nothing shown is dropped.
List<HomeRow> foldProcessingRuns(List<HomeRow> rows, {required String processingTitle}) {
  final folded = <HomeRow>[];
  var run = <HomeRow>[];
  void flush() {
    if (run.isEmpty) return;
    final first = run.length == 1 ? run.first : null;
    if (first != null && first.isProcessing && first.episode != null) {
      folded.add(first);
    } else {
      final members = <ServerConversation>[];
      final seen = <String>{};
      final ids = <String>{};
      for (final row in run) {
        ids.addAll(row.episodeConversationIds);
        final source = row.episode?.members.isNotEmpty == true ? row.episode!.members : [row.conversation];
        for (final member in source) {
          if (seen.add(member.id)) members.add(member);
        }
        if (row.episode == null) ids.add(row.conversation.id);
      }
      members.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
      folded.add(_processingRun(members, processingTitle,
          step: _leastAdvanced(run.map((r) => r.step ?? HomeStep.writingNotes)), ids: ids));
    }
    run = [];
  }

  for (final row in rows) {
    final step = row.step ?? (row.isProcessing ? HomeStep.writingNotes : homeStepOf(row.conversation));
    if (step == null || step == HomeStep.failed) {
      flush();
      folded.add(row);
      continue;
    }
    final current = row.step == step ? row : row.withStep(step);
    if (run.isNotEmpty && run.last.day != row.day) flush();
    run.add(current);
  }
  flush();
  return folded;
}

HomeStep _leastAdvanced(Iterable<HomeStep> steps) =>
    steps.fold(HomeStep.failed, (least, step) => step.index < least.index ? step : least);

/// The step a conversation row is waiting on, or null when it is finished and may show
/// as its own Home row. The server's `home_step` wins; older servers fall back to the
/// row's status, an empty capture, or a stand-in title. A [HomeStep.failed] result is
/// terminal and must never be folded into a processing run.
HomeStep? homeStepOf(ServerConversation c) {
  if (c.homeStep == 'failed') return HomeStep.failed;
  if (c.isLocked || c.discarded || c.deleted || c.clientProcessing != null || c.processingDeferred) return null;
  switch (c.homeStep) {
    case 'transcribing':
      return HomeStep.transcribing;
    case 'writing_notes':
      return HomeStep.writingNotes;
    case 'failed':
      return HomeStep.failed;
    case 'ready':
    case 'noise':
      return null;
  }
  if (c.status == ConversationStatus.failed) return HomeStep.failed;
  if (c.status == ConversationStatus.processing || c.status == ConversationStatus.merging) {
    // A server-batch capture still waiting for speech; otherwise the notes are being written.
    return c.structured.title == _serverTranscribingTitle || c.structured.title.trim().isEmpty
        ? HomeStep.transcribing
        : HomeStep.writingNotes;
  }
  if (c.status != ConversationStatus.completed) return null;
  if (awaitingHomeTranscript(c)) return HomeStep.transcribing;
  if (c.summaryRetryable) return HomeStep.failed;
  if (c.structured.hasProvisionalTitle) return HomeStep.writingNotes;
  return null;
}

/// Server-classified noise: a finished row with nothing worth showing on Home.
bool isHomeNoise(ServerConversation c) => c.homeStep == 'noise' && !c.isLocked;

/// The member's own record says it is terminal (ready, noise, failed, or locked). A local processing entry
/// for such a member cannot hold its episode in "Finishing up…", so a stale entry cannot keep the
/// episode on a processing row after its summary has landed.
bool _serverFinished(ServerConversation c) =>
    c.homeStep == 'ready' || c.homeStep == 'noise' || c.homeStep == 'failed' || c.isLocked;

/// The step an episode row may paint for a pending member: a member's failure never
/// becomes the episode's failed processing row; the episode keeps
/// waiting for its remaining members.
HomeStep _episodeStepOf(ServerConversation c) {
  final step = homeStepOf(c);
  return step == HomeStep.failed || step == null ? HomeStep.writingNotes : step;
}

/// backend `transcribing_hold.transcription_presentation`; read only when `home_step` is absent.
const _serverTranscribingTitle = 'Transcribing…';

HomeRow _processingRun(List<ServerConversation> members, String title,
    {Episode? episode, HomeStep step = HomeStep.transcribing, Set<String>? ids}) {
  final start = members.map((c) => c.startedAt ?? c.createdAt).reduce((a, b) => a.isBefore(b) ? a : b);
  final end = members.map((c) => c.finishedAt ?? c.startedAt ?? c.createdAt).reduce((a, b) => a.isAfter(b) ? a : b);
  final memberIds = {...members.map((c) => c.id), ...?ids};
  final parent = episode?.copyWith(members: members) ??
      Episode(
        id: '',
        live: false,
        startedAt: start,
        lastActivityAt: end,
        conversationIds: memberIds.toList(),
        members: members,
        title: title,
      );
  return HomeRow(
      ServerConversation(
        // A lone row keeps its own id, so its Home slot and key stay stable as it finishes.
        id: episode != null
            ? 'episode:${episode.id}'
            : (members.length == 1 ? members.single.id : 'processing-run:${members.last.id}'),
        createdAt: start,
        startedAt: start,
        finishedAt: end,
        structured: Structured(title, ''),
      ),
      episode: parent,
      episodeConversationIds: episode?.conversationIds.toSet() ?? memberIds,
      isProcessing: true,
      step: step,
      count: members.length);
}
