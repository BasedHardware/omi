import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/mobile/native_ui/ios_native_feedback.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

Person _person(String id, String name) => Person(
    id: id,
    name: name,
    createdAt: DateTime.utc(2026, 9, 1),
    updatedAt: DateTime.utc(2026, 9, 1),
    confidence: 'likely',
    voiceLearningState: 'learned');

GeneratedSpeakerTagPrompt _ownerCheck() => GeneratedSpeakerTagPrompt(
      id: 'prompt-owner',
      kind: 'owner_check',
      origin: 'unnamed',
      conversationId: 'c1',
      conversationTitle: 'Coffee chat',
      conversationStartedAt: DateTime.utc(2026, 10, 7, 9),
      speakerId: 1,
      segmentIds: const ['s1'],
      clipStart: 0,
      clipEnd: 8,
      excerpt: 'We should ship it on Friday',
    );

PersonVoiceMatch _match(String conversationId, String title) => PersonVoiceMatch(
    clipEnd: 4,
    clipStart: 0,
    conversationId: conversationId,
    matchLevel: 'close',
    segmentIds: const ['s1'],
    speakerId: 2,
    startedAt: DateTime.utc(2026, 10, 1, 9),
    talkSeconds: 42,
    title: title);

/// Simulator-only: flutter drive --driver integration_test/native_ui_host_driver.dart
/// --target integration_test/native_speaker_review_host_test.dart --flavor dev
/// --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('the Home speakers alert opens the native review; an answer shows the native Undo toast',
        (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final answers = <GeneratedSpeakerTagPromptAnswerRequest>[];
      final prompts = SpeakerTagPromptsProvider(
        fetchPrompts: () async => ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: [_ownerCheck()])),
        markShown: (_) async => const ApiSuccess(false),
        dismiss: () async => const ApiSuccess<void>(null),
        submitAnswer: (request) async {
          answers.add(request);
          return const ApiSuccess(GeneratedSpeakerTagPromptAnswerResponse(qualityOutcome: 'skipped'));
        },
        loadClip: (_) async => ApiSuccess(Uint8List(0)),
        emit: (_) {},
        answeredHold: Duration.zero,
      );
      addTearDown(prompts.dispose);
      await prompts.loadIfDue();
      final home = GlobalKey();
      // Home itself stays Flutter here so the sheet is the only native view; the alert is the one native
      // Home publishes, so its sheet wiring is what runs.
      await tester.pumpWidget(nativeHostApp(Scaffold(body: SizedBox.expand(key: home)),
          providers: [ChangeNotifierProvider<SpeakerTagPromptsProvider>.value(value: prompts)]));
      final alert = nativeHomeSpeakerReviewAlert(home.currentContext!);
      expect(alert.id, 'speakers');
      unawaited(Future<void>.sync(alert.perform));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-speaker-review-voice-matches-review-dark');
      expect(find.byType(NativeSpeakerReview), findsOneWidget);
      expect(nativeProjectedRow(tester, 'speaker_review_close').symbol, 'xmark');
      expect(nativeProjectedRow(tester, 'speaker_review_answer:not_a_person').enabled, isTrue);
      expect(NativeFeedbackHost.active, isTrue, reason: 'toasts present natively once the renderer is confirmed');

      await nativeProjectedRow(tester, 'speaker_review_answer:me').action!(null);
      await tester.pump(const Duration(seconds: 1));
      expect(prompts.pending?.answer, SpeakerTagAnswer.me, reason: 'staged while the native Undo toast is up');
      expect(NativeFeedbackHost.active, isTrue);
      expect(find.byType(SnackBar), findsNothing, reason: 'the Undo toast is native, not the Flutter SnackBar');
      expect(nativeProjectedRow(tester, 'speaker_review_answered').kind, 'label');
      // Inside the 5 s Undo window: the native toast floats above the sheet.
      await checkNativeHost(tester, 'native-speaker-review-voice-matches-toast-dark');
      // The harness waits past the Undo window, which closes on its own; the answer then commits once.
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(seconds: 1));
      expect(answers.single.answer, 'me');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the native transcript offers earlier voice matches, which open natively', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final conversation = ServerConversation(
        id: 'conversation-voices',
        createdAt: DateTime.utc(2026, 10, 7, 10),
        structured: Structured('Planning', 'We planned the week.'),
        status: ConversationStatus.completed,
        speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [1]),
        transcriptSegments: [
          TranscriptSegment(
              id: 's1',
              text: 'Morning everyone',
              speaker: 'SPEAKER_01',
              speakerId: 1,
              isUser: false,
              personId: 'p1',
              start: 0,
              end: 4,
              translations: const []),
        ],
      );
      final detail = ConversationDetailProvider(fetchConversation: (_) async => conversation)
        ..selectedDate = conversation.createdAt
        ..setCachedConversation(conversation);
      addTearDown(detail.dispose);
      final outcome = SpeakerTagOutcomeController(
        fetchPerson: (id) async => ApiSuccess(_person(id, 'Maya')),
        fetchMatches: (_) async => ApiSuccess([_match('a', 'Standup'), _match('b', 'Lunch')]),
        pollInterval: const Duration(milliseconds: 100),
      );
      addTearDown(outcome.dispose);
      var projected = <NativeRow>[];
      final people = [_person('p1', 'Maya')];
      final peopleProvider = PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))
        ..people = people;
      addTearDown(peopleProvider.dispose);
      await tester.pumpWidget(nativeHostApp(Scaffold(body: TranscriptWidgets(onNativePresentation: (sections) {
        projected = sections.expand((section) => section.rows).toList();
      })), providers: [
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
        ChangeNotifierProvider<PeopleProvider>.value(value: peopleProvider),
        ChangeNotifierProvider<SpeakerTagOutcomeController>.value(value: outcome),
      ]));
      outcome.follow(personId: 'p1', personName: 'Maya', linesLabeled: 1);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));

      expect(projected.map((row) => row.id), contains('detail_transcript_heading'));
      final matches = projected.singleWhere((row) => row.id == 'detail_speaker_matches');
      await matches.action!(null);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-speaker-review-voice-matches-matches-dark');
      expect(nativeProjectedRow(tester, 'voice_match_when:0').title, 'Standup');
      expect(nativeProjectedRow(tester, 'voice_match_yes:1').enabled, isTrue);
      expect(nativeProjectedRow(tester, 'voice_match_close').symbol, 'xmark');
      expect(tester.takeException(), isNull);
      outcome.dismiss();
      await tester.pumpWidget(const SizedBox());
    });
  });
}
