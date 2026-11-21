import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/schema/recording_speakers.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import '../helpers/reprocess_fakes.dart';

TranscriptSegment line(String id) => TranscriptSegment(
    id: id,
    text: 'Fixture $id',
    speaker: 'SPEAKER_1',
    speakerId: 1,
    isUser: false,
    personId: null,
    start: 0,
    end: 2,
    translations: []);
ServerConversation conversation() => ServerConversation(
    id: 'c1',
    createdAt: DateTime(2026),
    status: ConversationStatus.completed,
    structured: Structured('Title', 'Summary'),
    transcriptSegments: [line('a')]);
void select(ConversationDetailProvider p) {
  final c = conversation();
  p.selectedDate = c.createdAt;
  p.setCachedConversation(c);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  for (final complete in [true, false]) {
    test('detail retains recording coverage for sheet and saved feedback: $complete', () async {
      final p = ConversationDetailProvider(
        fetchRecording: (_) async =>
            RecordingTranscript([RecordingLine('c1', line('a'))], coverage: complete ? 'complete' : 'partial'),
        assignRecording: (_, __, {required personId, required wholeRecording, episodeId}) async =>
            ApiSuccess(1, truncated: !complete),
      );
      select(p);
      await p.loadRecordingTranscript();
      expect(p.recordingCoverageComplete, complete);
      p.beginSpeakerLabelingSession();
      expect(await p.startSpeakerAssignment(['a'], 'maya')!, isTrue);
      expect(p.speakerCoverageComplete, complete);
      p.dispose();
    });
  }
  testWidgets('rename supersedes running reprocess and leaves exactly one trailing regeneration', (tester) async {
    final running = Completer<ServerConversation?>();
    var regenerations = 0;
    final p = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true,
      reprocess: conversationReprocess((id, {appId, requireSpeakerReceipt = false}) {
        regenerations++;
        final updated = conversation()..transcriptSegments.single.personId = 'maya';
        return regenerations == 1 ? running.future : Future.value(updated);
      }),
    );
    select(p);
    final stale = p.reprocessConversation();
    await tester.pump();
    expect(p.loadingReprocessConversation, isTrue);
    p.beginSpeakerLabelingSession();
    final saved = p.startSpeakerAssignment(['a'], 'maya');
    expect(saved, isNotNull);
    expect(p.conversation.transcriptSegments.single.personId, 'maya');
    await tester.pump();
    expect(await saved!, isTrue);
    p.confirmSpeakerLabelingSession();
    running.complete(conversation());
    await tester.pump();
    expect(await stale, isFalse);
    expect(p.conversation.transcriptSegments.single.personId, 'maya');
    await tester.pump(const Duration(seconds: 4));
    await tester.pump();
    expect(regenerations, 2);
    p.dispose();
  });
  test('conversation cache and raw segment transports retain scoped voice identity', () {
    final c = conversation();
    c.transcriptSegments.single
      ..speakerIdScope = 'stream:1'
      ..speaker = 'SPEAKER_01';
    final restored = ServerConversation.fromJson(c.toJson());
    expect(restored.transcriptSegments.single.recordingVoice, ('stream:1', 'SPEAKER_1'));
    expect(TranscriptSegment.fromJson(c.transcriptSegments.single.toJson()).recordingVoice, ('stream:1', 'SPEAKER_1'));
  });
  test('rename before recording metadata arrives still proves and updates only one scoped voice', () async {
    final calls = <List<Map<String, dynamic>>>[];
    final p = ConversationDetailProvider(
        assignRecording: (_, selections, {required personId, required wholeRecording, episodeId}) async {
      calls.add(selections);
      return const ApiSuccess(1);
    });
    final c = conversation();
    c.transcriptSegments.single.speakerIdScope = 'first';
    c.transcriptSegments.add(line('b')..speakerIdScope = 'reconnect');
    p.selectedDate = c.createdAt;
    p.setCachedConversation(c);
    p.beginSpeakerLabelingSession();
    final saved = p.startSpeakerAssignment(['a'], 'maya', speakerId: 1)!;
    expect(c.transcriptSegments.map((s) => s.personId), ['maya', null]);
    expect(await saved, isTrue);
    expect(calls.single.single['voice'], {'speaker_id_scope': 'first', 'stream_speaker': 'SPEAKER_1'});
    p.dispose();
  });
  test('partial member failure rolls back only failed members', () async {
    final p = ConversationDetailProvider(
      fetchRecording: (_) async => RecordingTranscript([
        RecordingLine('c1', line('a'), scope: 's', label: 'SPEAKER_1'),
        RecordingLine('c2', line('b'), scope: 's', label: 'SPEAKER_1'),
      ]),
      assignRecording: (_, __, {required personId, required wholeRecording, episodeId}) async =>
          throw const PartialSpeakerAssignmentException({'c1'}, {'c2'}, 1, stale: true),
    );
    select(p);
    await p.loadRecordingTranscript();
    p.beginSpeakerLabelingSession();
    expect(await p.startSpeakerAssignment(['a', 'b'], 'maya')!, isFalse);
    expect(p.recordingSegments.map((s) => s.personId), ['maya', null]);
    expect(p.speakerAssignmentPartial, isTrue);
    expect(p.lastSpeakerAppliedCount, 1);
    p.dispose();
  });
  test('over-cap failure rolls back optimistic labels and exposes specific reason', () async {
    final p = ConversationDetailProvider(
      assignRecording: (_, __, {required personId, required wholeRecording, episodeId}) async =>
          const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 413)),
    );
    select(p);
    p.beginSpeakerLabelingSession();
    expect(await p.startSpeakerAssignment(['a'], 'maya')!, isFalse);
    expect(p.conversation.transcriptSegments.single.personId, isNull);
    expect(p.speakerAssignmentLimited, isTrue);
    p.dispose();
  });
  test('one recording request spans two members with optimistic rollback on stale 409', () async {
    final response = Completer<ApiResult<int>>();
    final calls = <List<Map<String, dynamic>>>[];
    final p = ConversationDetailProvider(
      fetchRecording: (_) async => RecordingTranscript([
        RecordingLine('c1', line('a'), scope: 'stream', label: 'SPEAKER_1'),
        RecordingLine('c2', line('b'), scope: 'stream', label: 'SPEAKER_1'),
      ], episodeId: 'episode'),
      assignRecording: (id, selections, {required personId, required wholeRecording, episodeId}) {
        calls.add(selections);
        expect(episodeId, 'episode');
        expect(wholeRecording, isFalse);
        return response.future;
      },
    );
    select(p);
    await p.loadRecordingTranscript();
    p.beginSpeakerLabelingSession();
    var failed = false;
    final saved = p.startSpeakerAssignment(['a', 'b'], 'maya', onFailed: () => failed = true)!;
    expect(p.recordingSegments.every((s) => s.personId == 'maya'), isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(calls, hasLength(1));
    expect(calls.single.map((e) => e['conversation_id']), ['c1', 'c2']);
    response.complete(const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409)));
    expect(await saved, isFalse);
    expect(p.recordingSegments.every((s) => s.personId == null), isTrue);
    expect(p.speakerAssignmentStale, isTrue);
    expect(failed, isTrue);
    p.dispose();
  });
  test('independent queued edits both persist', () async {
    final first = Completer<bool>();
    final calls = <List<String>>[];
    final p = ConversationDetailProvider(
        fetchConversation: (_) async => null,
        assignSpeaker: (_, ids, {isUser, personId, speakerId}) {
          calls.add(ids);
          return calls.length == 1 ? first.future : Future.value(true);
        });
    select(p);
    p.conversation.transcriptSegments.add(line('b'));
    p.beginSpeakerLabelingSession();
    final a = p.assignSpeaker(['a'], 'maya');
    final b = p.assignSpeaker(['b'], 'sam');
    await Future<void>.delayed(Duration.zero);
    first.complete(true);
    expect(await a, isTrue);
    expect(await b, isTrue);
    expect(calls, [
      ['a'],
      ['b']
    ]);
    p.dispose();
  });
  test('display positions and ids stay distinct without changing persistence identities', () async {
    final p = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true,
      fetchRecording: (_) async => RecordingTranscript([
        RecordingLine('c1', line('a'), scope: 'first', label: 'SPEAKER_1'),
        RecordingLine('c2', line('b'), scope: 'second', label: 'SPEAKER_1', offset: 60),
      ]),
    );
    select(p);
    await p.loadRecordingTranscript();
    expect(p.recordingDisplaySegments.map((line) => line.speakerId).toSet(), hasLength(2));
    expect(p.recordingDisplaySegments.last.start, 60);
    expect(p.recordingSegments.last.start, 0);
    expect(p.sourceSpeakerId('b', 99), 1);
    p.dispose();
  });
  test('large recordings reserve Omi identity while allocating display voices', () async {
    final p = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true,
      fetchRecording: (_) async => RecordingTranscript([
        RecordingLine('c1', line('omi')..speakerId = 99),
        for (var i = 0; i < 101; i++)
          RecordingLine('c$i', line(i == 1 ? 'a' : 'voice-$i'), scope: 'scope-$i', label: 'SPEAKER_1'),
      ]),
    );
    select(p);
    await p.loadRecordingTranscript();
    expect(p.recordingDisplaySegments.first.speakerId, 99);
    expect(p.recordingDisplaySegments.skip(1).any((line) => line.speakerId == 99), isFalse);
    expect(p.recordingDisplaySegments.skip(1).map((line) => line.speakerId).toSet(), hasLength(101));
    p.dispose();
  });
  test('recording metadata cannot hide a newer visible line', () async {
    final p = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true,
      fetchRecording: (_) async => RecordingTranscript([
        RecordingLine('c1', line('a'), scope: 'scope', label: 'SPEAKER_1'),
        RecordingLine('c2', line('b'), scope: 'scope', label: 'SPEAKER_1', offset: 60),
      ]),
    );
    select(p);
    p.conversation.transcriptSegments.add(line('newer')..start = 3);
    await p.loadRecordingTranscript();
    expect(p.recordingSegments.map((line) => line.id), contains('newer'));
    expect(p.recordingDisplaySegments.map((line) => line.id), contains('newer'));
    p.dispose();
  });
}
