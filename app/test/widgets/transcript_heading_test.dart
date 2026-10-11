import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart' show OmiCloseButton, OmiSheetScaffold;
import 'package:omi/utils/constants.dart';

const _explanation = 'Speaker labels may not match across the recordings in this conversation.';
const _sheetTitle = 'About Speaker Labels';
const _sheetBody =
    'Omi could not tell the other voices apart across the recordings. Tap a speaker label to name who is speaking.';

TranscriptSegment _seg(
  String id,
  int speakerId,
  double start, {
  bool isUser = false,
  String? personId,
  String text = 'speech',
}) =>
    TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_${speakerId.toString().padLeft(2, '0')}',
      speakerId: speakerId,
      isUser: isUser,
      personId: personId,
      start: start,
      end: start + 5,
      translations: const [],
    );

Person _person(String id, String name) =>
    Person(id: id, name: name, createdAt: DateTime(2026), updatedAt: DateTime(2026));

ServerConversation _conversation(List<TranscriptSegment> segments, {ConversationSpeakers? speakers}) =>
    ServerConversation(
      id: 'c-heading',
      createdAt: DateTime(2026, 9, 30, 12),
      structured: Structured('Title', 'Summary'),
      status: ConversationStatus.completed,
      transcriptSegments: segments,
      speakerResolution: speakers,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pumpDetail(
    WidgetTester tester,
    ServerConversation conversation, {
    List<Person> people = const [],
  }) async {
    final detail = ConversationDetailProvider(fetchConversation: (_) async => conversation)
      ..selectedDate = conversation.createdAt
      ..setCachedConversation(conversation);
    addTearDown(detail.dispose);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider<PeopleProvider>.value(
            value: PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))..people = people,
          ),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidgets()),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  String headingLabel(WidgetTester tester) {
    final heading = find.byKey(const Key('conversation_transcript_heading'));
    expect(heading, findsOneWidget);
    return tester
        .widgetList<Text>(find.descendant(of: heading, matching: find.byType(Text)))
        .map((text) => text.data ?? '')
        .join();
  }

  group('transcript heading speaker count', () {
    testWidgets('an unavailable resolution shows no speaker count even with many raw ids', (tester) async {
      final segments = [for (var i = 0; i < 11; i++) _seg('s$i', i, i * 5.0)];
      await pumpDetail(tester, _conversation(segments, speakers: const ConversationSpeakers(status: 'unavailable')));

      expect(headingLabel(tester), 'Transcript');
    });

    testWidgets('missing metadata shows no speaker count', (tester) async {
      final segments = [for (var i = 0; i < 11; i++) _seg('s$i', i, i * 5.0)];
      await pumpDetail(tester, _conversation(segments));

      expect(headingLabel(tester), 'Transcript');
    });

    testWidgets('a resolved count uses participants plus the owner, ignoring other raw ids', (tester) async {
      final segments = [
        _seg('own', 0, 0, isUser: true),
        _seg('p1a', 1, 10),
        _seg('p1b', 2, 20),
        _seg('noise-30', 30, 30),
        _seg('noise-31', 31, 40),
        _seg('noise-40', 40, 50),
      ];
      await pumpDetail(
        tester,
        _conversation(
          segments,
          speakers: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [1, 2]),
        ),
      );

      expect(headingLabel(tester), 'Transcript · 3 speakers');
    });

    testWidgets('the owner counts once across raw ids, duplicate participant ids once', (tester) async {
      final segments = [
        _seg('own-a', 0, 0, isUser: true),
        _seg('own-b', 5, 10, isUser: true),
        _seg('p1', 1, 20),
        _seg('noise', 30, 30),
      ];
      await pumpDetail(
        tester,
        _conversation(
          segments,
          speakers: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0, 5, 1, 1]),
        ),
      );

      expect(headingLabel(tester), 'Transcript · 2 speakers');
    });

    testWidgets('the same person across participant ids counts once, another person still counts', (tester) async {
      final segments = [
        _seg('own', 0, 0, isUser: true),
        _seg('a1', 1, 10, personId: 'p1'),
        _seg('a2', 2, 20, personId: 'p1'),
        _seg('b', 3, 30, personId: 'p2'),
      ];
      await pumpDetail(
        tester,
        _conversation(
          segments,
          speakers: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [1, 2, 3]),
        ),
        people: [_person('p1', 'Ada'), _person('p2', 'Ada')],
      );

      expect(headingLabel(tester), 'Transcript · 3 speakers');
    });

    testWidgets('Omi is not counted as a speaker', (tester) async {
      final segments = [_seg('own', 0, 0, isUser: true), _seg('p1', 1, 10), _seg('omi', omiSpeakerId, 20)];
      await pumpDetail(
        tester,
        _conversation(
          segments,
          speakers: const ConversationSpeakers(status: 'capture', participantSpeakerIds: [1]),
        ),
      );

      expect(headingLabel(tester), 'Transcript · 2 speakers');
    });

    testWidgets('an unknown future status omits the count', (tester) async {
      final segments = [_seg('own', 0, 0, isUser: true), _seg('p1', 1, 10)];
      await pumpDetail(
        tester,
        _conversation(
          segments,
          speakers: const ConversationSpeakers(status: 'v3-multimodal', participantSpeakerIds: [1]),
        ),
      );

      expect(headingLabel(tester), 'Transcript');
    });
  });

  group('unresolved speaker explanation', () {
    testWidgets('shows once when an unnamed voice remains, taps open About Speaker Labels', (tester) async {
      final semantics = tester.ensureSemantics();
      final segments = [_seg('own', 0, 0, isUser: true), _seg('anon', 1, 10)];
      await pumpDetail(tester, _conversation(segments, speakers: const ConversationSpeakers(status: 'unavailable')));

      final explanation = find.text(_explanation);
      expect(explanation, findsOneWidget);

      final notice = find.byKey(const Key('transcript_unresolved_speakers_notice'));
      expect(notice, findsOneWidget);
      expect(tester.getSize(notice).height, greaterThanOrEqualTo(44));
      expect(tester.getSemantics(notice).getSemanticsData().hasAction(SemanticsAction.tap), isTrue);

      await tester.tap(notice);
      await tester.pumpAndSettle();

      expect(find.byType(OmiSheetScaffold), findsOneWidget);
      expect(find.text(_sheetTitle), findsOneWidget);
      expect(find.text(_sheetBody), findsOneWidget);
      expect(find.text('Try Again'), findsNothing);
      expect(find.text('Retry'), findsNothing);

      await tester.tap(find.descendant(of: find.byType(OmiSheetScaffold), matching: find.byType(OmiCloseButton)));
      await tester.pumpAndSettle();
      expect(find.text(_sheetTitle), findsNothing);
      semantics.dispose();
    });

    testWidgets('is absent when the resolution is countable', (tester) async {
      final segments = [_seg('own', 0, 0, isUser: true), _seg('anon', 1, 10)];
      await pumpDetail(
        tester,
        _conversation(
          segments,
          speakers: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [1]),
        ),
      );

      expect(find.text(_explanation), findsNothing);
    });

    testWidgets('is absent when every voice is the owner, Omi, or named', (tester) async {
      final segments = [
        _seg('own', 0, 0, isUser: true),
        _seg('omi', omiSpeakerId, 10),
        _seg('named', 1, 20, personId: 'p1'),
      ];
      await pumpDetail(
        tester,
        _conversation(segments, speakers: const ConversationSpeakers(status: 'unavailable')),
        people: [_person('p1', 'Ada')],
      );

      expect(find.text(_explanation), findsNothing);
    });

    testWidgets('a missing or blank-named person still counts as unnamed', (tester) async {
      final segments = [_seg('missing', 1, 0, personId: 'gone'), _seg('blank', 2, 10, personId: 'p-blank')];
      await pumpDetail(
        tester,
        _conversation(segments, speakers: const ConversationSpeakers(status: 'unavailable')),
        people: [_person('p-blank', '  ')],
      );

      expect(find.text(_explanation), findsOneWidget);
    });
  });
}
