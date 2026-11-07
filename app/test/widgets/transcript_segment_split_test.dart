import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/recording_speakers.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/edit_segment_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/recording_speaker_fixtures.dart';

void main() {
  setUpAll(() => Env.init(RecordingSpeakerFixtureEnv()));

  Future<void> setupSharedPreferences({List<Map<String, dynamic>>? cachedPeople}) async {
    final values = <String, Object>{};
    if (cachedPeople != null) {
      values['cachedPeople'] = cachedPeople.map((p) => jsonEncode(p)).toList();
    }
    SharedPreferences.setMockInitialValues(values);
    await SharedPreferencesUtil.init();
  }

  group('TranscriptSegment.splitAtOffset', () {
    test('splits mixed-speaker segment at word boundary with proportional timing and preserved metadata', () {
      final segment = TranscriptSegment(
        id: 'seg-1',
        text: 'Hello there. General Kenobi.',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: 'person-1',
        start: 10.0,
        end: 20.0,
        translations: const [],
        speechProfileProcessed: true,
        speakerLabelSource: 'manual',
      );

      final offset = 'Hello there. '.length;
      final result = segment.splitAtOffset(offset, secondSegmentId: 'seg-1__split_1');

      expect(result.isSuccess, isTrue);
      expect(result.failure, isNull);
      expect(result.first!.id, 'seg-1');
      expect(result.first!.text, 'Hello there.');
      expect(result.first!.originalText, 'Hello there.');
      expect(result.first!.start, 10.0);
      expect(result.first!.end, greaterThan(10.0));
      expect(result.first!.end, lessThan(20.0));
      expect(result.first!.personId, 'person-1');
      expect(result.first!.speakerLabelSource, 'manual');

      expect(result.second!.id, 'seg-1__split_1');
      expect(result.second!.text, 'General Kenobi.');
      expect(result.second!.originalText, 'General Kenobi.');
      expect(result.second!.start, result.first!.end);
      expect(result.second!.end, 20.0);
      expect(result.second!.personId, 'person-1');
      expect(result.second!.speakerLabelSource, 'manual');

      final segments = [result.first!, result.second!];
      expect(TranscriptSegment.canDisplaySeconds(segments), isTrue);
      final exported = TranscriptSegment.segmentsAsString(
        segments,
        includeTimestamps: true,
        people: [
          Person(
            id: 'person-1',
            name: 'Obi-Wan',
            createdAt: DateTime.utc(2026, 1, 1),
            updatedAt: DateTime.utc(2026, 1, 1),
          ),
        ],
      );
      expect(exported, contains('Hello there.'));
      expect(exported, contains('General Kenobi.'));
    });

    test('returns failure for empty sides, mid-word offsets, or missing timing evidence', () {
      final segment = TranscriptSegment(
        id: 'seg-1',
        text: 'Hello world',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: null,
        start: 0.0,
        end: 4.0,
        translations: const [],
      );

      expect(segment.splitAtOffset(0).failure, TranscriptSegmentSplitFailure.emptySide);
      expect(segment.splitAtOffset(segment.text.length).failure, TranscriptSegmentSplitFailure.emptySide);
      expect(segment.splitAtOffset(2).failure, TranscriptSegmentSplitFailure.midWordBoundary);

      final unTimed = TranscriptSegment(
        id: 'seg-untimed',
        text: 'Hello world',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: null,
        start: 5.0,
        end: 5.05,
        translations: const [],
      );
      expect(unTimed.splitAtOffset(5).failure, TranscriptSegmentSplitFailure.insufficientTiming);
    });
  });

  group('Saved transcript split UI and independent speaker assignment', () {
    testWidgets('EditSegmentSheet surfaces clear limit messages when split boundary or timing is invalid',
        (tester) async {
      await setupSharedPreferences();
      final unTimedSegment = TranscriptSegment(
        id: 'seg-short',
        text: 'Hello world',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: null,
        start: 2.0,
        end: 2.05,
        translations: const [],
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: buildOmiTheme(brightness: Brightness.dark),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: EditSegmentSheet(
              segment: unTimedSegment,
              onSave: (_) {},
              onSplit: (offset, editedText) async =>
                  unTimedSegment.splitAtOffset(offset, editedText: editedText),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Place cursor inside a word first to test midWordBoundary
      final textField = tester.widget<TextField>(find.byKey(const Key('edit_segment_text_field')));
      textField.controller!.selection = const TextSelection.collapsed(offset: 2);
      await tester.tap(find.byKey(const Key('split_segment_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('split_segment_error')), findsOneWidget);
      expect(find.text('Place the cursor at a word boundary before splitting.'), findsOneWidget);

      // Place cursor at word boundary on short-timing segment to test insufficientTiming
      textField.controller!.selection = const TextSelection.collapsed(offset: 5);
      await tester.tap(find.byKey(const Key('split_segment_button')));
      await tester.pumpAndSettle();
      expect(find.text('This segment is too short to split cleanly.'), findsOneWidget);
    });

    testWidgets('splits saved mixed-speaker segment into two turns and assigns each turn independently',
        (tester) async {
      final now = DateTime.utc(2026, 1, 1);
      final maya = Person(id: 'maya', name: 'Maya', createdAt: now, updatedAt: now);
      final alex = Person(id: 'alex', name: 'Alex', createdAt: now, updatedAt: now);
      await setupSharedPreferences(
        cachedPeople: [
          {'id': 'maya', 'name': 'Maya', 'created_at': now.toIso8601String(), 'updated_at': now.toIso8601String()},
          {'id': 'alex', 'name': 'Alex', 'created_at': now.toIso8601String(), 'updated_at': now.toIso8601String()},
        ],
      );

      final mixedSegment = TranscriptSegment(
        id: 'seg-mixed',
        text: 'First speaker part. Second speaker reply.',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: 'maya',
        start: 0.0,
        end: 10.0,
        translations: const [],
        speakerLabelSource: 'manual',
      );

      final conversation = ServerConversation(
        id: 'conv-1',
        createdAt: now,
        status: ConversationStatus.completed,
        structured: Structured('Title', 'Summary'),
        transcriptSegments: [mixedSegment],
      );

      final splitCalls = <(String, String, TranscriptSegment, TranscriptSegment)>[];
      final assignRequests = <ApiRequest>[];

      final detail = ConversationDetailProvider(
        fetchConversation: (_) async => conversation,
        reprocess: (_) async => conversation,
        fetchRecording: (_) async => RecordingTranscript(
          [RecordingLine('conv-1', mixedSegment, scope: 'scope', label: 'SPEAKER_01')],
          episodeId: 'ep-1',
          coverage: 'complete',
        ),
        splitSegment: (conversationId, segmentId, first, second) async {
          splitCalls.add((conversationId, segmentId, first, second));
          return true;
        },
        assignRecording: (id, selections, {required personId, required wholeRecording, episodeId}) =>
            assignRecordingSpeakers(
          id,
          selections,
          personId: personId,
          wholeRecording: wholeRecording,
          episodeId: episodeId,
          send: (request) async {
            assignRequests.add(request);
            return http.Response(
              jsonEncode({
                'coverage': 'complete',
                'applied_count': 1,
                'conversations': [
                  {'conversation_id': 'conv-1', 'applied_count': 1},
                ],
              }),
              200,
            );
          },
        ),
      )..selectedDate = conversation.createdAt;
      detail.setCachedConversation(conversation);

      final people = PeopleProvider(loadPeople: () async => PeopleListResponse(people: [maya, alex]))
        ..people = [maya, alex];
      final outcome = SpeakerTagOutcomeController(
        fetchPerson: (id) async => ApiSuccess(id == 'alex' ? alex : maya),
        fetchMatches: (_) async => const ApiSuccess([]),
      );

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: detail),
            ChangeNotifierProvider.value(value: people),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider.value(value: outcome),
          ],
          child: MaterialApp(
            theme: buildOmiTheme(brightness: Brightness.dark),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const Scaffold(body: TranscriptWidgets()),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();

      expect(find.text('First speaker part. Second speaker reply.', findRichText: true), findsOneWidget);

      // Split the mixed segment at the boundary between sentences
      final splitOffset = 'First speaker part. '.length;
      final splitResult = await detail.splitEditingSegment(0, splitOffset);
      expect(splitResult.isSuccess, isTrue);
      await tester.pumpAndSettle();

      expect(splitCalls, hasLength(1));
      expect(detail.conversation.transcriptSegments, hasLength(2));
      expect(detail.recordingSegments, hasLength(2));
      final firstId = detail.conversation.transcriptSegments[0].id;
      final secondId = detail.conversation.transcriptSegments[1].id;
      expect(firstId, 'seg-mixed');
      expect(secondId, startsWith('seg-mixed__split_'));
      expect(detail.isSplitTurnSegment(firstId), isTrue);
      expect(detail.isSplitTurnSegment(secondId), isTrue);

      // Both resulting turns are rendered with their own turn header and edit speaker button
      expect(find.text('First speaker part.', findRichText: true), findsOneWidget);
      expect(find.text('Second speaker reply.', findRichText: true), findsOneWidget);
      expect(find.byKey(ValueKey('edit_speaker_label_$firstId')), findsOneWidget);
      expect(find.byKey(ValueKey('edit_speaker_label_$secondId')), findsOneWidget);

      // Reassign the second split turn to Alex via Select lines without overwriting the first turn (Maya)
      await tester.tap(find.byKey(const Key('transcript_select_lines')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(ValueKey('transcript_select_$secondId')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('speaker_labeling_assign')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('speaker_quick_picker_person_alex')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();

      expect(assignRequests, hasLength(1));
      final body = jsonDecode(assignRequests.single.body) as Map<String, dynamic>;
      expect(body['whole_recording'], isFalse);
      expect(detail.conversation.transcriptSegments[0].personId, 'maya');
      expect(detail.conversation.transcriptSegments[1].personId, 'alex');
      expect(find.text('Maya'), findsOneWidget);
      expect(find.text('Alex'), findsOneWidget);

      detail.leaveSpeakerLabelingSession('conv-1');
      await tester.pump(const Duration(seconds: 6));
      await tester.pumpWidget(const SizedBox.shrink());
      outcome.dispose();
      people.dispose();
      detail.dispose();
    });

    test('rolls back optimistic split when persistence fails', () async {
      await setupSharedPreferences();
      final now = DateTime.utc(2026, 1, 1);
      final segment = TranscriptSegment(
        id: 'seg-rollback',
        text: 'Part one. Part two.',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: null,
        start: 0.0,
        end: 6.0,
        translations: const [],
      );
      final conversation = ServerConversation(
        id: 'conv-rollback',
        createdAt: now,
        status: ConversationStatus.completed,
        structured: Structured('Title', 'Summary'),
        transcriptSegments: [segment],
      );
      final detail = ConversationDetailProvider(
        fetchConversation: (_) async => conversation,
        splitSegment: (_, __, ___, ____) async => false,
      )..selectedDate = now;
      detail.setCachedConversation(conversation);

      final result = await detail.splitEditingSegment(0, 'Part one. '.length);
      expect(result.isSuccess, isFalse);
      expect(result.failure, TranscriptSegmentSplitFailure.persistenceFailed);
      expect(detail.conversation.transcriptSegments, hasLength(1));
      expect(detail.conversation.transcriptSegments.single.id, 'seg-rollback');
      expect(detail.conversation.transcriptSegments.single.text, 'Part one. Part two.');
      detail.dispose();
    });
  });
}
