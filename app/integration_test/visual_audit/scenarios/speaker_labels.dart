// Speaker labels in a transcript: how a label was made (confirmed, likely, unnamed), rejecting a
// wrong one, what tagging a person came to (lines labeled, voice learned or not, the same voice in
// earlier conversations), and a label carried into the next live conversation.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/transcript.dart';

import '../fakes.dart';
import '../harness.dart';
import 'capture.dart';

const _transcript = 'lib/pages/conversation_detail/widgets/transcript_tab.dart (TranscriptWidgets)';
const _live = 'lib/pages/conversation_capturing/page.dart (ConversationCapturingPage)';

Person _person(String id, String name, {String voice = 'learned'}) => Person(
      id: id,
      name: name,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
      voiceReadiness: voice == 'learned' ? 'ready' : 'not_learned',
      voiceLearningState: voice,
    );

TranscriptSegment _line(int index, String text, int speaker, {bool isUser = false, String? personId, String? source}) =>
    TranscriptSegment(
      id: 's$index',
      text: text,
      speaker: 'SPEAKER_$speaker',
      isUser: isUser,
      personId: personId,
      start: index * 6.0,
      end: index * 6.0 + 5,
      translations: [],
      speakerLabelSource: source,
    );

Future<PeopleProvider> _people() async {
  final people = PeopleProvider(
    loadPeople: () async =>
        PeopleListResponse(people: [_person('p-maya', 'Maya Chen'), _person('p-jordan', 'Jordan Lee')]),
  );
  await people.setPeople();
  return people;
}

/// The real detail page on its Transcript tab, with label writes answered locally.
Future<void> _pumpTranscript(
  AuditRun a,
  ServerConversation conversation, {
  SpeakerTagOutcomeController? outcome,
}) async {
  final people = await a.tester.runAsync(_people);
  await a.pump(
    ConversationDetailPage(conversation: conversation, initialTab: ConversationTab.transcript),
    providers: <SingleChildWidget>[
      ChangeNotifierProvider<PeopleProvider>.value(value: people!),
      ChangeNotifierProvider<ConversationProvider>.value(
        value: ConversationProvider(isSignedIn: () => true)..conversations = [conversation],
      ),
      ChangeNotifierProvider(
        create: (_) => ConversationDetailProvider(
          assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true,
          rejectSpeaker: (_, __, ___, {personId, segmentIds}) async => ApiSuccess(conversation),
          reprocess: (_, {appId, requireSpeakerReceipt = false}) async => conversation,
          fetchConversation: (_) async => conversation,
        )..selectedDate = conversationLocalDayKey(conversation.createdAt),
      ),
      if (outcome != null) ChangeNotifierProvider<SpeakerTagOutcomeController>.value(value: outcome),
    ],
  );
}

final _earlier = [
  PersonVoiceMatch(
    conversationId: 'c-lunch',
    title: 'Lunch planning',
    startedAt: DateTime.now().subtract(const Duration(days: 1)),
    speakerId: 2,
    talkSeconds: 840,
    segmentIds: const ['e1'],
    clipStart: 12,
    clipEnd: 20,
    matchLevel: 'strong',
  ),
  PersonVoiceMatch(
    conversationId: 'c-call',
    title: 'Friday call',
    startedAt: DateTime.now().subtract(const Duration(days: 3)),
    speakerId: 1,
    talkSeconds: 372,
    segmentIds: const ['e2'],
    clipStart: 40,
    clipEnd: 48,
    matchLevel: 'likely',
  ),
];

ServerConversation _unnamedConversation(String id) => auditConversation(id, title: 'Catching up over lunch', segments: [
      _line(0, 'I have been playing out every weekend since July.', 1),
      _line(1, 'That is a lot of weekends.', 0, isUser: true, source: 'auto'),
      _line(2, 'Six gigs since my birthday, and one of them was a festival slot.', 1),
      _line(3, 'The label manager set most of them up.', 1),
    ]);

/// The detail transcript opens at its last line; the label states start at the first.
Future<void> _scrollToTop(AuditRun a) async {
  final list = find.descendant(of: find.byType(TranscriptWidget), matching: find.byType(Scrollable)).first;
  a.tester.state<ScrollableState>(list).position.jumpTo(0);
  await a.settle();
}

Future<void> _tagFirstSpeakerAsMaya(AuditRun a) async {
  await _scrollToTop(a);
  await a.tap(find.text('Speaker 1').first);
  await a.tap(find.text('Maya Chen'));
  await a.tap(find.byType(Checkbox).first);
  await a.tap(find.text('Save'));
}

/// The live page with one voice whose label was carried in from the previous conversation.
class _CarriedCaptureProvider extends AuditCaptureProvider {
  _CarriedCaptureProvider() : super(AuditLive.pendant);

  @override
  List<TranscriptSegment> get segments => _segments;
  final _segments = [
    _line(0, 'Okay, now it should summarize what we just talked about.', 0, isUser: true, source: 'auto'),
    _line(1, 'I like how it wrote down my joke.', 1, personId: 'p-maya', source: 'carried'),
    _line(2, 'It is going to remember that now.', 0, isUser: true, source: 'auto'),
    _line(3, 'So you run engineering at a company that makes hardware?', 1, personId: 'p-maya', source: 'carried'),
  ];
}

final speakerLabelScenarios = <AuditScenario>[
  AuditScenario(
    id: 'speaker-labels-transcript',
    title: 'Transcript labels: confirmed, likely and unnamed',
    page: _transcript,
    state: 'Maya labeled by the user, Jordan and the owner matched by voice, one unnamed speaker',
    run: (a) async {
      final conversation = auditConversation('labels', title: 'Catching up over lunch', segments: [
        _line(0, 'I have been playing out every weekend since July.', 1, personId: 'p-maya', source: 'manual'),
        _line(1, 'That is a lot of weekends.', 0, isUser: true, source: 'auto'),
        _line(2, 'The festival is the one I really want to play.', 2, personId: 'p-jordan', source: 'auto'),
        _line(3, 'The label has been pushing for it all year.', 2, personId: 'p-jordan', source: 'auto'),
        _line(4, 'Table for three?', 3),
      ]);
      await _pumpTranscript(a, conversation);
      await _scrollToTop(a);
      expect(find.byKey(const Key('speaker_label_confirmed')), findsOneWidget);
      expect(find.byKey(const Key('speaker_label_likely')), findsOneWidget);
      expect(find.byKey(const Key('speaker_likely_confirm')), findsOneWidget);
      await a.shot('Open the transcript: a check on the label you made, Likely on the one Omi guessed', step: 'labels');

      await a.tap(find.byKey(const Key('speaker_likely_not')));
      expect(find.byKey(const Key('speaker_likely_confirm')), findsNothing);
      expect(find.text('Jordan Lee'), findsNothing);
      await a.shot('Tap Not Jordan Lee: every line from that voice loses the label', step: 'rejected');

      await a.tap(find.text('Maya Chen').first);
      expect(find.byKey(const Key('name_speaker_not_person')), findsOneWidget);
      await a.shot('Tap a labeled name: the tag sheet also offers Not Maya Chen and Not a Person', step: 'sheet');
    },
  ),
  AuditScenario(
    id: 'speaker-labels-tag-outcome',
    title: 'After tagging: lines labeled, voice learned, earlier conversations',
    page: _transcript,
    state: 'An unnamed speaker tagged as Maya; the server reports the voice learned and two earlier matches',
    run: (a) async {
      final outcome = SpeakerTagOutcomeController(
        fetchPerson: (id) async => ApiSuccess(_person(id, 'Maya Chen')),
        fetchMatches: (_) async => ApiSuccess(_earlier),
        pollInterval: const Duration(seconds: 3),
      );
      await _pumpTranscript(a, _unnamedConversation('outcome'), outcome: outcome);
      await _tagFirstSpeakerAsMaya(a);
      expect(find.byKey(const Key('speaker_tag_outcome_voice_pending')), findsOneWidget);
      await a.shot('Tag Speaker 1 as Maya Chen: the card says what the tag did while the voice is learned',
          step: 'learning');

      await a.tester.pump(const Duration(seconds: 3));
      await a.settle();
      expect(find.byKey(const Key('speaker_tag_outcome_voice_learned')), findsOneWidget);
      await a.shot('A few seconds later: voice learned, and the same voice is in two earlier conversations',
          step: 'learned');

      await a.tap(find.byKey(const Key('speaker_tag_outcome_review')));
      await a.shot('Tap Review: one answer per earlier conversation', step: 'review');
      outcome.dismiss();
    },
  ),
  AuditScenario(
    id: 'speaker-labels-tag-outcome-more-speech',
    title: 'After tagging: voice not learned yet',
    page: _transcript,
    state: 'An unnamed speaker tagged as Maya; the server reports too little clear speech',
    run: (a) async {
      final outcome = SpeakerTagOutcomeController(
        fetchPerson: (id) async => ApiSuccess(_person(id, 'Maya Chen', voice: 'needs_more_speech')),
        fetchMatches: (_) async => const ApiSuccess([]),
        pollInterval: const Duration(milliseconds: 100),
      );
      await _pumpTranscript(a, _unnamedConversation('outcome-short'), outcome: outcome);
      await _tagFirstSpeakerAsMaya(a);
      expect(find.byKey(const Key('speaker_tag_outcome_voice_needs_more_speech')), findsOneWidget);
      await a.shot('Tag a speaker with little clear speech: the card says why the voice was not learned');
      outcome.dismiss();
    },
  ),
  AuditScenario(
    id: 'speaker-labels-carried-live',
    title: 'Live page: a label carried over from the last conversation',
    page: _live,
    state: 'The pendant records; Maya was labeled in the previous conversation of the same recording',
    run: (a) async {
      final people = await a.tester.runAsync(_people);
      await a.pump(const ConversationCapturingPage(), scaffold: false, providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: _CarriedCaptureProvider()),
        ChangeNotifierProvider<PeopleProvider>.value(value: people!),
        ChangeNotifierProvider<DeviceProvider>.value(
            value: AuditDeviceProvider(connected: true, battery: 72, device: auditPendant)),
      ]);
      expect(find.byKey(const Key('carried_speaker_banner')), findsOneWidget);
      await a.shot('A new conversation starts on the same recording: Maya is still Maya, with Change');
    },
  ),
];
