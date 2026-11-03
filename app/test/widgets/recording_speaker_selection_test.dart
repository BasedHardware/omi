import 'package:omi/env/env.dart';
import '../helpers/recording_speaker_fixtures.dart';
import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/schema/recording_speakers.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/reprocess_fakes.dart';

TranscriptSegment line(String id) => TranscriptSegment(
    id: id,
    text: 'Fixture line $id',
    speaker: 'SPEAKER_1',
    speakerId: 1,
    isUser: false,
    personId: null,
    start: 0,
    end: 2,
    translations: []);
void main() {
  setUpAll(() => Env.init(RecordingSpeakerFixtureEnv()));
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  for (final scenario in [(false, false), (true, false), (false, true)]) {
    final stale = scenario.$1;
    final partial = scenario.$2;
    testWidgets('cross-recording selection makes one episode call, stale=$stale, partial=$partial', (tester) async {
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final requests = <ApiRequest>[];
      final ongoing = Completer<ServerConversation?>();
      final maya = Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026));
      final conversation = ServerConversation(
          id: 'c1',
          createdAt: DateTime(2026),
          status: ConversationStatus.completed,
          structured: Structured('Title', 'Summary'),
          transcriptSegments: [line('a')]);
      final detail = ConversationDetailProvider(
        fetchConversation: (_) async => conversation,
        fetchRecording: (_) async => RecordingTranscript([
          RecordingLine('c1', line('a'), scope: 'scope', label: 'SPEAKER_1'),
          if (!partial) RecordingLine('c2', line('b'), scope: 'scope', label: 'SPEAKER_1'),
        ], episodeId: partial ? null : 'episode', coverage: partial ? 'partial' : 'complete'),
        assignRecording: (id, selections, {required personId, required wholeRecording, episodeId}) =>
            assignRecordingSpeakers(id, selections,
                personId: personId, wholeRecording: wholeRecording, episodeId: episodeId, send: (request) async {
          requests.add(request);
          return http.Response(
              stale
                  ? '{"detail":{"code":"stale_speaker"}}'
                  : jsonEncode({
                      'coverage': partial ? 'partial' : 'complete',
                      'applied_count': partial ? 1 : 2,
                      'conversations': [
                        {'conversation_id': 'c1', 'applied_count': 1},
                        if (!partial) {'conversation_id': 'c2', 'applied_count': 1}
                      ]
                    }),
              stale ? 409 : 200);
        }),
        reprocess: conversationReprocess((id, {appId, requireSpeakerReceipt = false}) => ongoing.future),
      )..selectedDate = conversation.createdAt;
      detail.setCachedConversation(conversation);
      final people = PeopleProvider(loadPeople: () async => PeopleListResponse(people: [maya]))..people = [maya];
      final outcome = SpeakerTagOutcomeController(
          fetchPerson: (_) async => ApiSuccess(maya), fetchMatches: (_) async => const ApiSuccess([]));
      await tester.pumpWidget(MultiProvider(
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
              home: const Scaffold(body: TranscriptWidgets()))));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      // An in-flight summary must leave the list and the selection action editable.
      unawaited(detail.reprocessConversation());
      await tester.pump();
      expect(find.text('Fixture line a', findRichText: true), findsOneWidget);
      await tester.tap(find.byKey(const Key('transcript_select_lines')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('transcript_select_a')));
      if (!partial) await tester.tap(find.byKey(const ValueKey('transcript_select_b')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      await tester.tap(find.byKey(const Key('speaker_labeling_assign')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      await tester.tap(find.byKey(const Key('speaker_quick_picker_person_maya')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      expect(requests, hasLength(1));
      expect(Uri.parse(requests.single.url).path,
          endsWith(partial ? 'v1/conversations/c1/recording-speakers' : 'v1/episodes/episode/assign-speaker'));
      expect(requests.single.method, 'PATCH');
      final body = jsonDecode(requests.single.body);
      expect((body['selections'] as List).map((s) => s['conversation_id']), partial ? ['c1'] : ['c1', 'c2']);
      expect(body['whole_recording'], isFalse);
      expect(detail.recordingSegments.every((s) => s.personId == (stale ? null : 'maya')), isTrue);
      if (partial) expect(find.text('Renamed 1 line in this conversation only.'), findsOneWidget);
      if (stale) expect(find.text('The speaker changed. Select the lines again.'), findsOneWidget);
      ongoing.complete(null);
      await tester.pump();
      detail.leaveSpeakerLabelingSession('c1');
      await tester.pump();
      await tester.pump(const Duration(seconds: 6));
      await tester.pumpWidget(const SizedBox.shrink());
      outcome.dispose();
      people.dispose();
      detail.dispose();
    });
  }
}
