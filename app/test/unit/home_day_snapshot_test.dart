import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/home/day_snapshot.dart';

void main() {
  final day = DateTime(2026, 7, 15);
  final other = DateTime(2026, 7, 14);

  HomeDaySnapshot snapshot({
    List<ServerConversation>? conversations,
    List<ActionItemWithMetadata> tasks = const [],
    List<LocalRecording> recordings = const [],
    DateTime? on,
    int shortThreshold = 120,
    DateTime? now,
  }) {
    return buildHomeDaySnapshot(
      day: on ?? day,
      conversations: conversations ?? [_conversation('a', 'Standup', day, 600)],
      tasks: tasks,
      recordings: recordings,
      shortThreshold: shortThreshold,
      isNewUser: false,
      now: now ?? DateTime(2026, 7, 15, 12),
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

    test('splits the day on the short threshold and orders it newest first', () {
      final result = snapshot(
        conversations: [
          _conversation('late', 'Roadmap sync', day.add(const Duration(hours: 13)), 600),
          _conversation('early', 'Standup', day.add(const Duration(hours: 9)), 600),
          _conversation('blip', 'yeah ok', day.add(const Duration(hours: 10)), 6),
        ],
      );

      expect(result.entries.map((e) => e.conversation?.id), ['late', 'early']);
      expect(result.shortOnes.map((c) => c.id), ['blip']);
      expect(result.conversations.map((c) => c.id), ['late', 'blip', 'early']);
    });

    test('changes when the short-conversation threshold changes', () {
      // Otherwise the collapsed/expanded split would keep the old partition
      // until something unrelated moved.
      expect(snapshot(shortThreshold: 120), isNot(snapshot(shortThreshold: 900)));
    });

    test('changes when the wall clock crosses midnight', () {
      // Due markers read Overdue/Today/Tomorrow against the current day, so the
      // same task means something different tomorrow.
      expect(
        snapshot(now: DateTime(2026, 7, 15, 23, 59)),
        isNot(snapshot(now: DateTime(2026, 7, 16, 0, 1))),
      );
    });

    test('changes when a conversation start time moves within the day', () {
      final before = [_conversation('a', 'Standup', day.add(const Duration(hours: 9)), 600)];
      final after = [_conversation('a', 'Standup', day.add(const Duration(hours: 10)), 600)];

      expect(snapshot(conversations: before), isNot(snapshot(conversations: after)));
    });

    test('places a recording waiting to be transcribed in the day it happened', () {
      // Without this a day spent recording offline reads as empty on home until
      // the files upload, while the conversations tab shows them sitting there.
      final result = snapshot(
        conversations: [_conversation('convo', 'Standup', day.add(const Duration(hours: 9)), 600)],
        recordings: [_recording('rec', day.add(const Duration(hours: 11)))],
      );

      expect(result.entries, hasLength(2));
      expect(result.entries.first.recording?.id, 'rec', reason: 'newest first, so 11am leads');
      expect(result.entries.last.conversation?.id, 'convo');
      expect(result.isEmpty, isFalse);
    });

    test('keeps a recording out of the collapsed short group', () {
      // A short conversation is noise; an untranscribed recording is a thing
      // the user still has to act on, so it is never folded away.
      final result = snapshot(
        conversations: const [],
        recordings: [_recording('blip', day.add(const Duration(hours: 9)), seconds: 6)],
      );

      expect(result.entries.single.recording?.id, 'blip');
      expect(result.shortOnes, isEmpty);
    });

    test('changes when a recording finishes uploading', () {
      final pending = [_recording('rec', day, state: LocalRecordingState.pending)];
      final processing = [_recording('rec', day, state: LocalRecordingState.processing)];

      expect(snapshot(recordings: pending), isNot(snapshot(recordings: processing)));
    });

    test('ignores recordings from another day', () {
      final result = snapshot(recordings: [_recording('elsewhere', other)]);

      expect(result.recordings, isEmpty);
    });

    test('a day of only short conversations is not an empty day', () {
      // Its entries are empty because everything folded into shortOnes, but the
      // day still happened — calling it empty contradicts the line counting it.
      final result = snapshot(
        conversations: [_conversation('blip', 'yeah ok', day.add(const Duration(hours: 9)), 6)],
      );

      expect(result.entries, isEmpty);
      expect(result.shortOnes, hasLength(1));
      expect(result.isEmpty, isFalse);
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

LocalRecording _recording(
  String id,
  DateTime startedAt, {
  int seconds = 600,
  LocalRecordingState state = LocalRecordingState.pending,
}) {
  return LocalRecording(
    fileName: id,
    filePath: '/tmp/$id',
    timerStart: startedAt.millisecondsSinceEpoch ~/ 1000,
    codec: BleAudioCodec.opus,
    frameSize: 160,
    sizeBytes: 1024,
    seconds: seconds,
    state: state,
  );
}

ActionItemWithMetadata _task(String id, String description, {String? conversationId, bool completed = false}) =>
    ActionItemWithMetadata(id: id, description: description, completed: completed, conversationId: conversationId);
