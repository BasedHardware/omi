// Regression for the 1.0.587 Transcript tab RangeError: the loading spinner row
// must always carry an id, so loading a recording transcript renders cleanly.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
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
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/recording_speaker_fixtures.dart';

TranscriptSegment _line(String id) => TranscriptSegment(
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

  testWidgets('loading a recording transcript shows the spinner row without a list error', (tester) async {
    final recording = Completer<RecordingTranscript>();
    final conversation = ServerConversation(
        id: 'c1',
        createdAt: DateTime(2026),
        status: ConversationStatus.completed,
        structured: Structured('Title', 'Summary'),
        transcriptSegments: [_line('a')]);
    final detail = ConversationDetailProvider(
      fetchConversation: (_) async => conversation,
      fetchRecording: (_) => recording.future,
    )..selectedDate = conversation.createdAt;
    detail.setCachedConversation(conversation);
    final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []));
    final outcome = SpeakerTagOutcomeController(
        fetchPerson: (_) async =>
            ApiSuccess(Person(id: 'p', name: 'P', createdAt: DateTime(2026), updatedAt: DateTime(2026))),
        fetchMatches: (_) async => const ApiSuccess([]));
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

    for (var attempt = 0; attempt < 3; attempt++) {
      unawaited(detail.loadRecordingTranscript());
      await tester.pump();
      expect(detail.loadingRecordingTranscript, isTrue);
      expect(detail.isReprocessingOpenConversation, isFalse);
      expect(tester.takeException(), isNull);
      expect(find.byKey(const ValueKey('transcript-leading-speaker-summary-updating')), findsOneWidget);
      expect(find.text('Fixture line a', findRichText: true), findsOneWidget);
    }

    recording.complete(RecordingTranscript([RecordingLine('c1', _line('a'), scope: 'scope', label: 'SPEAKER_1')],
        episodeId: 'episode', coverage: 'complete'));
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('transcript-leading-speaker-summary-updating')), findsNothing);
    expect(find.text('Fixture line a', findRichText: true), findsOneWidget);
  });
}
