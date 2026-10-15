import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_quick_picker.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/widgets/transcript.dart';

TranscriptSegment _line(String id, int speakerId, String text, double start, {String? personId}) => TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_${speakerId.toString().padLeft(2, '0')}',
      speakerId: speakerId,
      isUser: false,
      personId: personId,
      start: start,
      end: start + 2,
      translations: const [],
    );

Person _person(String id, String name) =>
    Person(id: id, name: name, createdAt: DateTime(2026), updatedAt: DateTime(2026));

Widget _app(Widget child, {List<SingleChildWidget> providers = const [], List<Person> people = const []}) =>
    MultiProvider(
      providers: [
        ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
        ChangeNotifierProvider<PeopleProvider>.value(
          value: PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))..people = people,
        ),
        ...providers,
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: child),
      ),
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('short lines inside a turn start where the long lines start', (tester) async {
    const long = 'We should look at the floor plan again before we decide anything about the kitchen.';
    final segments = [
      _line('a', 1, long, 0),
      _line('b', 1, 'Maybe', 3),
      _line('c', 2, 'Yeah, and the people inside so big. No.', 5),
      _line('d', 2, 'No.', 8),
      _line('e', 1, long, 10),
      _line('f', 1, 'Okay', 13),
    ];
    await tester.pumpWidget(
      _app(TranscriptWidget(segments: segments, isConversationDetail: true, horizontalMargin: false)),
    );
    await tester.pumpAndSettle();

    final start = tester.getTopLeft(find.text(long, findRichText: true).first).dx;
    for (final text in ['Maybe', 'Yeah, and the people inside so big. No.', 'No.', 'Okay']) {
      final line = find.text(text, findRichText: true);
      expect(line, findsOneWidget, reason: text);
      expect(tester.getTopLeft(line).dx, start, reason: '"$text" must not be centered');
      expect(tester.widget<RichText>(line).textAlign, TextAlign.left, reason: text);
    }
  });

  group('labeling pass', () {
    late ServerConversation conversation;
    late ConversationDetailProvider detail;
    late SpeakerTagOutcomeController outcome;
    late List<(String, String?)> saves;
    late int regenerations;

    // Built inside each test body, not setUp: the provider's save chain starts from a
    // completed future, and a future created outside the test's fake-async zone
    // resumes on the real microtask queue, which pumping never drains.
    void createPass() {
      conversation = ServerConversation(
        id: 'c-pass',
        createdAt: DateTime(2026, 10, 10, 9),
        structured: Structured('Title', 'Summary'),
        status: ConversationStatus.completed,
        transcriptSegments: [
          _line('a', 1, 'First line from the first voice.', 0),
          _line('b', 2, 'A reply from the second voice.', 3),
          _line('c', 1, 'The first voice again.', 6),
        ],
      );
      saves = [];
      regenerations = 0;
      detail = ConversationDetailProvider(
        assignSpeaker: (_, ids, {isUser, personId, speakerId}) async {
          saves.add((ids.join(','), personId));
          return true;
        },
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          regenerations++;
          return conversation;
        },
        fetchConversation: (_) async => conversation,
      )
        ..selectedDate = conversation.createdAt
        ..setCachedConversation(conversation);
      outcome = SpeakerTagOutcomeController(
        fetchPerson: (id) async => ApiSuccess(_person(id, 'Maya')),
        fetchMatches: (_) async => const ApiSuccess([]),
      );
    }

    Future<void> pumpTab(WidgetTester tester) async {
      createPass();
      await tester.pumpWidget(
        _app(
          const TranscriptWidgets(),
          people: [_person('maya', 'Maya')],
          providers: [
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
            ChangeNotifierProvider<SpeakerTagOutcomeController>.value(value: outcome),
          ],
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> finish(WidgetTester tester) async {
      outcome.dismiss();
      await tester.pumpWidget(const SizedBox());
      detail.dispose();
      outcome.dispose();
    }

    testWidgets('select lines, name them with one tap, and Done updates the summary once', (tester) async {
      await pumpTab(tester);
      expect(find.byKey(const Key('speaker_labeling_session_bar')), findsNothing);

      await tester.tap(find.byKey(const Key('transcript_select_lines')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('speaker_labeling_session_bar')), findsOneWidget);
      expect(find.text('0 selected'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('transcript_select_a')));
      await tester.tap(find.byKey(const ValueKey('transcript_select_c')));
      await tester.pumpAndSettle();
      expect(find.text('2 selected'), findsOneWidget);

      await tester.tap(find.byKey(const Key('speaker_labeling_assign')));
      await tester.pumpAndSettle();
      expect(find.byType(SpeakerQuickPicker), findsOneWidget);
      await tester.tap(find.byKey(const Key('speaker_quick_picker_person_maya')));
      await tester.pumpAndSettle();

      expect(find.byType(SpeakerQuickPicker), findsNothing);
      expect(saves, [('a,c', 'maya')]);
      expect(find.text('Labeled 2 lines'), findsOneWidget);
      // The per-label card waits for Done; pauses between labels regenerate nothing.
      expect(find.byKey(const Key('speaker_tag_outcome')), findsNothing);
      await tester.pump(const Duration(seconds: 10));
      expect(regenerations, 0);

      await tester.tap(find.byKey(const Key('speaker_labeling_done')));
      // The outcome card's "Learning voice…" spinner never settles; pump past the regeneration.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(regenerations, 1);
      expect(find.byKey(const Key('speaker_labeling_session_bar')), findsNothing);
      expect(find.byKey(const Key('speaker_tag_outcome')), findsOneWidget);
      await finish(tester);
    });

    testWidgets('selection mode toggles lines instead of opening the name sheet; Cancel leaves it', (tester) async {
      await pumpTab(tester);
      await tester.tap(find.byKey(const Key('transcript_select_lines')));
      await tester.pumpAndSettle();
      // The name sits under the line's toggle, so the tap selects instead of opening the sheet.
      await tester.tap(find.text('Speaker 1').first, warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.text('1 selected'), findsOneWidget);
      expect(find.byType(NameSpeakerBottomSheet), findsNothing);

      await tester.tap(find.byKey(const Key('speaker_labeling_cancel_selection')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('transcript_select_a')), findsNothing);
      // The pass stays open with nothing labeled, and Done regenerates nothing.
      await tester.tap(find.byKey(const Key('speaker_labeling_done')));
      await tester.pumpAndSettle();
      expect(regenerations, 0);
      await finish(tester);
    });

    testWidgets('Undo in the bar puts the previous label back', (tester) async {
      await pumpTab(tester);
      await tester.tap(find.byKey(const Key('transcript_select_lines')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('transcript_select_b')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('speaker_labeling_assign')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('speaker_quick_picker_person_maya')));
      await tester.pumpAndSettle();
      expect(conversation.transcriptSegments[1].personId, 'maya');

      await tester.tap(find.byKey(const Key('speaker_labeling_undo')));
      await tester.pumpAndSettle();
      expect(conversation.transcriptSegments[1].personId, isNull);
      expect(saves.last, ('b', null));
      expect(find.text('Labeled 0 lines'), findsOneWidget);
      await finish(tester);
    });
  });

  test('the quick picker puts people already in the conversation first, then recent, then by name', () {
    final people = [_person('zoe', 'Zoe'), _person('amy', 'Amy'), _person('maya', 'Maya'), _person('blank', ' ')];
    final ordered = SpeakerQuickPicker.order(
      people,
      [_line('a', 1, 'x', 0, personId: 'maya'), _line('b', 1, 'y', 1, personId: 'maya')],
      {'zoe': 100},
    );
    expect(ordered.map((p) => p.id), ['maya', 'zoe', 'amy']);
  });
}
