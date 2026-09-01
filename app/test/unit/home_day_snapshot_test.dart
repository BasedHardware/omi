import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/home/day_snapshot.dart';

void main() {
  final day = DateTime(2026, 7, 15);
  final other = DateTime(2026, 7, 14);

  HomeDaySnapshot snapshot({
    List<ServerConversation>? conversations,
    List<ActionItemWithMetadata> tasks = const [],
    DateTime? on,
    int shortThreshold = 120,
  }) {
    return buildHomeDaySnapshot(
      day: on ?? day,
      conversations: conversations ?? [_conversation('a', 'Standup', day, 600)],
      tasks: tasks,
      shortThreshold: shortThreshold,
      isNewUser: false,
    );
  }

  group('home day snapshot', () {
    test('is equal across rebuilds when nothing it renders changed', () {
      // The whole point: providers notify constantly, so an unchanged day must
      // not force the timeline (and the day's map) to rebuild.
      expect(snapshot(), snapshot());
    });

    test('changes when a task on the day is completed', () {
      final open = _task('t1', 'Prep perf numbers', conversationId: 'a');
      final done = _task('t1', 'Prep perf numbers', conversationId: 'a', completed: true);

      expect(snapshot(tasks: [open]), isNot(snapshot(tasks: [done])));
    });

    test('ignores tasks belonging to other days', () {
      final elsewhere = _task('t9', 'Not this day', conversationId: 'somewhere-else');

      expect(snapshot(tasks: [elsewhere]), snapshot());
      expect(snapshot(tasks: [elsewhere]).tasksByConversation, isEmpty);
    });

    test('changes when a conversation gains a location the map would draw', () {
      final plain = [_conversation('a', 'Standup', day, 600)];
      final located = [_conversation('a', 'Standup', day, 600, latitude: 37.7, longitude: -122.4)];

      expect(snapshot(conversations: plain), isNot(snapshot(conversations: located)));
    });

    test('splits the day on the short threshold and keeps it in order', () {
      final result = snapshot(
        conversations: [
          _conversation('late', 'Roadmap sync', day.add(const Duration(hours: 13)), 600),
          _conversation('early', 'Standup', day.add(const Duration(hours: 9)), 600),
          _conversation('blip', 'yeah ok', day.add(const Duration(hours: 10)), 6),
        ],
      );

      expect(result.highlights.map((c) => c.id), ['early', 'late']);
      expect(result.shortOnes.map((c) => c.id), ['blip']);
      expect(result.conversations.map((c) => c.id), ['early', 'blip', 'late']);
    });

    test('keeps only the selected day', () {
      final result = snapshot(
        conversations: [
          _conversation('today', 'Standup', day, 600),
          _conversation('yesterday', 'Older', other, 600),
        ],
      );

      expect(result.conversations.map((c) => c.id), ['today']);
    });
  });
}

ServerConversation _conversation(
  String id,
  String title,
  DateTime startedAt,
  int seconds, {
  double? latitude,
  double? longitude,
}) {
  return ServerConversation(
    id: id,
    createdAt: startedAt,
    startedAt: startedAt,
    structured: Structured(title, 'Overview', emoji: '🧠'),
    geolocation: latitude == null ? null : Geolocation(latitude: latitude, longitude: longitude),
    transcriptSegments: [
      TranscriptSegment(
        id: '$id-0',
        text: 'x',
        speaker: 'SPEAKER_0',
        isUser: false,
        personId: null,
        start: 0,
        end: seconds.toDouble(),
        translations: const [],
      ),
    ],
  );
}

ActionItemWithMetadata _task(String id, String description, {String? conversationId, bool completed = false}) =>
    ActionItemWithMetadata(id: id, description: description, completed: completed, conversationId: conversationId);
