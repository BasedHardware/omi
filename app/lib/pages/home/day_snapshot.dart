import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/schema.dart';
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
    required this.highlights,
    required this.shortOnes,
    required this.tasksByConversation,
    required this.isNewUser,
    required this.fingerprint,
  });

  /// Every conversation of the day in the order it happened, short and
  /// discarded ones included — they still carry the day's map locations.
  final List<ServerConversation> conversations;

  /// The day's real conversations, and the ones folded behind the short line.
  final List<ServerConversation> highlights;
  final List<ServerConversation> shortOnes;

  final Map<String, List<ActionItemWithMetadata>> tasksByConversation;
  final bool isNewUser;

  /// Identity of the rendered state: two snapshots that agree here paint the
  /// same pixels, so the page can skip the rebuild.
  final String fingerprint;

  bool get isEmpty => conversations.isEmpty;

  @override
  bool operator ==(Object other) => other is HomeDaySnapshot && other.fingerprint == fingerprint;

  @override
  int get hashCode => fingerprint.hashCode;
}

/// Builds the day's view state and its fingerprint in one pass.
///
/// Only tasks belonging to the day's own conversations are carried, so a task
/// edited on another day cannot force the timeline to rebuild.
HomeDaySnapshot buildHomeDaySnapshot({
  required DateTime day,
  required List<ServerConversation> conversations,
  required List<ActionItemWithMetadata> tasks,
  required int shortThreshold,
  required bool isNewUser,
}) {
  final dayConversations = conversations
      .where((conversation) => conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt) == day)
      .toList()
    // The day reads top to bottom the way it was lived.
    ..sort((a, b) => (a.startedAt ?? a.createdAt).compareTo(b.startedAt ?? b.createdAt));

  final highlights = <ServerConversation>[];
  final shortOnes = <ServerConversation>[];
  final dayConversationIds = <String>{};
  final fingerprint = StringBuffer()
    ..write(day.toIso8601String())
    ..write(isNewUser);

  for (final conversation in dayConversations) {
    final seconds = conversation.getDurationInSeconds();
    (conversation.discarded || seconds < shortThreshold ? shortOnes : highlights).add(conversation);
    dayConversationIds.add(conversation.id);
    final geolocation = conversation.geolocation;
    fingerprint
      ..write('|c:')
      ..write(conversation.id)
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

  return HomeDaySnapshot(
    conversations: dayConversations,
    highlights: highlights,
    shortOnes: shortOnes,
    tasksByConversation: tasksByConversation,
    isNewUser: isNewUser,
    fingerprint: fingerprint.toString(),
  );
}
