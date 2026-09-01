import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/widgets/conversations_group_widget.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Everything the home day view renders for one day, plus a fingerprint of the
/// inputs it came from.
///
/// Home listens to two providers that notify on every websocket tick,
/// conversation reconciliation pass and task refresh. Rebuilding the timeline —
/// and with it the day's map — on each of those is wasted work, so the page
/// selects this value and rebuilds only when the fingerprint moves.
@immutable
class HomeDaySnapshot {
  const HomeDaySnapshot({
    required this.conversations,
    required this.recordings,
    required this.entries,
    required this.shortOnes,
    required this.tasksByConversation,
    required this.isNewUser,
    required this.fingerprint,
  });

  /// Every conversation of the day in the order it happened, short and
  /// discarded ones included — they still carry the day's map locations.
  final List<ServerConversation> conversations;

  /// The day's Transcribe Later captures, still on the phone. They carry their
  /// own start-location snapshot, so they belong to the header's map too.
  final List<LocalRecording> recordings;

  /// The day as it is rendered, in the order it happened: its conversations
  /// interleaved with recordings still waiting to be transcribed.
  final List<ConversationGroupEntry> entries;

  /// Conversations folded behind the short-conversations line. Recordings are
  /// never folded away — an untranscribed one is asking the user for something.
  final List<ServerConversation> shortOnes;

  final Map<String, List<ActionItemWithMetadata>> tasksByConversation;
  final bool isNewUser;

  /// Identity of the rendered state: two snapshots that agree here paint the
  /// same pixels, so the page can skip the rebuild.
  final String fingerprint;

  bool get isEmpty => entries.isEmpty;

  @override
  bool operator ==(Object other) => other is HomeDaySnapshot && other.fingerprint == fingerprint;

  @override
  int get hashCode => fingerprint.hashCode;
}

/// Builds the day's view state and its fingerprint in one pass.
///
/// Only tasks belonging to the day's own conversations are carried, so a task
/// edited on another day cannot force the timeline to rebuild.
///
/// [recordings] are Transcribe Later captures still on the phone. They belong
/// on the day they were recorded even though no conversation exists for them
/// yet — without them a day spent recording offline reads as empty until the
/// files upload and transcribe.
HomeDaySnapshot buildHomeDaySnapshot({
  required DateTime day,
  required List<ServerConversation> conversations,
  required List<ActionItemWithMetadata> tasks,
  required int shortThreshold,
  required bool isNewUser,
  List<LocalRecording> recordings = const [],
  DateTime? now,
}) {
  final current = now ?? DateTime.now();
  final dayConversations = conversations
      .where((conversation) => conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt) == day)
      .toList()
    // The day reads top to bottom the way it was lived.
    ..sort((a, b) => (a.startedAt ?? a.createdAt).compareTo(b.startedAt ?? b.createdAt));

  final dayRecordings = recordings.where((recording) => conversationLocalDayKey(recording.startedAt) == day).toList();

  final highlights = <ServerConversation>[];
  final shortOnes = <ServerConversation>[];
  final dayConversationIds = <String>{};
  final fingerprint = StringBuffer()
    ..write(day.toIso8601String())
    ..write(isNewUser)
    // Which conversations are collapsed depends on this, and it changes when
    // the user edits the short-conversation setting.
    ..write(shortThreshold)
    // Due markers read "Overdue"/"Today"/"Tomorrow" relative to the wall clock,
    // so the same task means something different after midnight.
    ..write(DateTime(current.year, current.month, current.day).toIso8601String());

  for (final conversation in dayConversations) {
    final seconds = conversation.getDurationInSeconds();
    (conversation.discarded || seconds < shortThreshold ? shortOnes : highlights).add(conversation);
    dayConversationIds.add(conversation.id);
    final geolocation = conversation.geolocation;
    fingerprint
      ..write('|c:')
      ..write(conversation.id)
      // Reconciliation can move a conversation's start within the same day,
      // changing both its printed time and its place in the order.
      ..write((conversation.startedAt ?? conversation.createdAt).millisecondsSinceEpoch)
      ..write(seconds)
      ..write(conversation.discarded)
      ..write(conversation.structured.title)
      // The header's map and place name are built from these.
      ..write(geolocation?.latitude)
      ..write(geolocation?.longitude)
      ..write(geolocation?.address);
  }

  final tasksByConversation = <String, List<ActionItemWithMetadata>>{};
  for (final task in tasks) {
    final conversationId = task.conversationId;
    if (conversationId == null || !dayConversationIds.contains(conversationId)) continue;
    tasksByConversation.putIfAbsent(conversationId, () => []).add(task);
    fingerprint
      ..write('|t:')
      ..write(task.id)
      ..write(task.completed)
      ..write(task.description)
      ..write(task.dueAt?.millisecondsSinceEpoch);
  }

  for (final recording in dayRecordings) {
    fingerprint
      ..write('|r:')
      ..write(recording.id)
      ..write(recording.state.name)
      ..write(recording.seconds)
      ..write(recording.geolocation?.latitude)
      ..write(recording.geolocation?.longitude);
  }

  return HomeDaySnapshot(
    conversations: dayConversations,
    recordings: dayRecordings,
    // The conversations page already defines what "everything that happened
    // that day, in order" means; reusing it keeps home from drifting into a
    // second answer. That helper orders newest first, home reads forwards.
    entries: buildConversationGroupEntries(conversations: highlights, recordings: dayRecordings).reversed.toList(),
    shortOnes: shortOnes,
    tasksByConversation: tasksByConversation,
    isNewUser: isNewUser,
    fingerprint: fingerprint.toString(),
  );
}
