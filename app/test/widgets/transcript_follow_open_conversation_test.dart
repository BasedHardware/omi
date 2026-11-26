// The conversation page's transcript, while its conversation is still in progress, keeps the newest
// line in view: stored lines and the live words under them alike. A reader who scrolls away is left
// where they are and gets a way back; a conversation that has ended is never moved.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/transcript.dart';

import '../helpers/recording_speaker_fixtures.dart';

const _jump = ValueKey('transcript_jump_to_latest');

TranscriptSegment _stored(int i) => TranscriptSegment(
      id: 'stored-$i',
      text: 'Stored line $i with enough words to fill a row of the transcript.',
      speaker: 'SPEAKER_0${i % 2}',
      isUser: i.isEven,
      personId: null,
      start: i * 10.0,
      end: i * 10.0 + 5,
      translations: const [],
    );

List<TranscriptSegment> _storedLines(int count) => [for (var i = 0; i < count; i++) _stored(i)];

void main() {
  setUpAll(() => Env.init(RecordingSpeakerFixtureEnv()));
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('the list', () {
    late ScrollController controller;
    late List<TranscriptSegment> segments;
    late ValueNotifier<int> liveLines;
    late bool follow;

    setUp(() {
      segments = _storedLines(40);
      liveLines = ValueNotifier(2);
      follow = true;
    });

    tearDown(() => liveLines.dispose());

    // The live words rebuild on their own, as the page's do: the list is not rebuilt for them.
    Widget liveWords() => ValueListenableBuilder<int>(
          valueListenable: liveLines,
          builder: (context, count, _) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var i = 0; i < count; i++)
                Padding(padding: const EdgeInsets.only(bottom: 8), child: Text('live words $i', key: Key('live-$i'))),
            ],
          ),
        );

    Future<void> pump(WidgetTester tester, {bool settle = true, bool reducedMotion = false, bool live = true}) async {
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(disableAnimations: reducedMotion),
            child: child!,
          ),
          home: Scaffold(
            body: SizedBox(
              height: 420,
              child: TranscriptWidget(
                key: const ValueKey('open-conversation'),
                segments: segments,
                isConversationDetail: true,
                bottomMargin: 150,
                followLatest: follow,
                jumpToLatestButtonBottom: 120,
                onScrollControllerReady: (value) => controller = value,
                contentVersion: identityHashCode(segments),
                trailingItem: live ? liveWords() : null,
              ),
            ),
          ),
        ),
      );
      if (settle) await tester.pumpAndSettle();
    }

    double end() => controller.position.maxScrollExtent;
    void expectAtEnd() => expect(controller.offset, closeTo(end(), 0.5));

    Future<void> scrollUp(WidgetTester tester, [double by = 300]) async {
      await tester.drag(find.byType(ListView), Offset(0, by));
      await tester.pumpAndSettle();
    }

    testWidgets('opens at its newest line, with no jump button', (tester) async {
      await pump(tester);

      expect(end(), greaterThan(1000));
      expectAtEnd();
      expect(find.byKey(const Key('live-1')).hitTestable(), findsOneWidget);
      expect(find.byKey(_jump), findsNothing);
    });

    // What the reader can see: nothing while the list is being placed, the list once it is.
    bool painted(WidgetTester tester) =>
        tester.widget<Opacity>(find.ancestor(of: find.byType(ListView), matching: find.byType(Opacity)).first).opacity >
        0;

    /// Pumps frames without letting time pass (no animation can advance) and requires every frame
    /// the reader sees to show the end of the list.
    Future<void> expectPlacedUnseen(WidgetTester tester) async {
      var shown = false;
      for (var frame = 0; frame < 30 && !shown; frame++) {
        await tester.pump();
        shown = painted(tester);
        if (shown) expectAtEnd();
      }
      expect(shown, isTrue, reason: 'the list was never shown');
      await tester.pump();
      expectAtEnd();
      expect(tester.binding.hasScheduledFrame, isFalse);
    }

    testWidgets('opens already at its newest line: nothing is painted on the way there', (tester) async {
      await pump(tester, settle: false);
      expect(painted(tester), isFalse);

      await expectPlacedUnseen(tester);
      expect(find.byKey(_jump), findsNothing);
    });

    testWidgets('lines that load after the page opened are placed the same way, unseen', (tester) async {
      // The page opens with what the conversation list knew: no lines, only the live words.
      segments = [];
      await pump(tester);
      expect(painted(tester), isTrue);

      segments = _storedLines(120);
      await pump(tester, settle: false);
      expect(painted(tester), isFalse);
      await expectPlacedUnseen(tester);
      expect(end(), greaterThan(4000));
    });

    testWidgets('a long stretch arriving at once is placed, not travelled', (tester) async {
      await pump(tester);
      final before = end();

      // Back from the background: many lines at once, the end is several screens away.
      segments = [...segments, for (var i = 40; i < 100; i++) _stored(i)];
      await pump(tester, settle: false);
      for (var frame = 0; frame < 30; frame++) {
        await tester.pump();
      }

      expect(end(), greaterThan(before + 2000));
      expectAtEnd();
    });

    testWidgets('new words under the reader travel to the end instead of snapping', (tester) async {
      await pump(tester);
      final before = controller.offset;

      liveLines.value = 4;
      // No other widget asks for frames here: the follow must start on its own.
      await tester.pump();
      expect(tester.binding.hasScheduledFrame, isTrue);
      for (var frame = 0; frame < 10 && controller.offset <= before; frame++) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      // Mid-flight: the list has left its old end and not yet reached the new one.
      expect(controller.offset, greaterThan(before));
      expect(controller.offset, lessThan(end() - 1));
      expect(find.byKey(_jump), findsNothing);

      await tester.pumpAndSettle();
      expectAtEnd();
      expect(find.byKey(_jump), findsNothing);
    });

    testWidgets('a new stored line keeps the end in view', (tester) async {
      await pump(tester);
      final before = end();

      segments = [...segments, _stored(40), _stored(41)];
      await pump(tester);

      expect(end(), greaterThan(before + 20));
      expectAtEnd();
      expect(find.byKey(_jump), findsNothing);
    });

    testWidgets('live words growing under the stored lines keep the end in view', (tester) async {
      await pump(tester);
      final before = end();

      for (var count = 3; count <= 12; count++) {
        liveLines.value = count;
        await tester.pump();
        await tester.pump();
      }
      await tester.pumpAndSettle();

      expect(end(), greaterThan(before + 100));
      expectAtEnd();
      expect(find.byKey(const Key('live-11')).hitTestable(), findsOneWidget);
    });

    testWidgets('a conversation with only live words so far follows them once they fill the page', (tester) async {
      segments = [];
      liveLines.value = 1;
      await pump(tester);
      expect(end(), 0);

      liveLines.value = 40;
      await tester.pumpAndSettle();

      expect(end(), greaterThan(300));
      expectAtEnd();
    });

    testWidgets('stored lines replacing live words keep the end in view', (tester) async {
      liveLines.value = 12;
      await pump(tester);
      expectAtEnd();

      // The transcribed lines arrive and the live words they cover go away in the same update.
      segments = [...segments, _stored(40)];
      liveLines.value = 1;
      await pump(tester);

      expectAtEnd();
      expect(find.byKey(_jump), findsNothing);
    });

    testWidgets('a reader who scrolled up is left in place and gets a way back', (tester) async {
      await pump(tester);
      await scrollUp(tester);
      final held = controller.offset;
      expect(held, lessThan(end() - 200));
      expect(find.byKey(_jump), findsOneWidget);

      segments = [...segments, _stored(40)];
      await pump(tester);
      liveLines.value = 10;
      await tester.pumpAndSettle();

      expect(controller.offset, closeTo(held, 0.5));
      expect(find.byKey(_jump), findsOneWidget);

      await tester.tap(find.byKey(_jump));
      await tester.pumpAndSettle();
      expectAtEnd();
      expect(find.byKey(_jump), findsNothing);

      // Back at the end, the follow is on again.
      liveLines.value = 16;
      await tester.pumpAndSettle();
      expectAtEnd();
    });

    testWidgets('scrolling back to the end by hand resumes the follow', (tester) async {
      await pump(tester);
      await scrollUp(tester);
      expect(find.byKey(_jump), findsOneWidget);

      await tester.drag(find.byType(ListView), const Offset(0, -600));
      await tester.pumpAndSettle();
      expectAtEnd();
      expect(find.byKey(_jump), findsNothing);

      segments = [...segments, _stored(40)];
      await pump(tester);
      liveLines.value = 9;
      await tester.pumpAndSettle();
      expectAtEnd();
    });

    testWidgets('new words during a drag do not move the list under the finger', (tester) async {
      await pump(tester);
      final gesture = await tester.startGesture(tester.getCenter(find.byType(ListView)));
      for (var step = 0; step < 4; step++) {
        await gesture.moveBy(const Offset(0, 40));
        await tester.pump(const Duration(milliseconds: 16));
      }
      final held = controller.offset;
      expect(held, lessThan(end() - 100));

      liveLines.value = 10;
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 16));
      segments = [...segments, _stored(40)];
      await pump(tester, settle: false);
      await tester.pump(const Duration(milliseconds: 16));

      expect(controller.offset, closeTo(held, 0.5));

      await gesture.up();
      await tester.pumpAndSettle();
      expect(controller.offset, lessThan(end() - 100));
      expect(find.byKey(_jump), findsOneWidget);
    });

    testWidgets('a small nudge that ends near the end keeps following', (tester) async {
      await pump(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 30));
      await tester.pumpAndSettle();
      expect(end() - controller.offset, lessThanOrEqualTo(24));

      liveLines.value = 10;
      await tester.pumpAndSettle();
      expectAtEnd();
    });

    testWidgets('when the conversation ends the list stays where it is and stops following', (tester) async {
      await pump(tester);
      expectAtEnd();
      final held = controller.offset;

      follow = false;
      segments = [...segments, _stored(40), _stored(41), _stored(42)];
      await pump(tester, live: false);

      expect(controller.offset, closeTo(held.clamp(0, end()), 0.5));
      expect(find.byKey(_jump), findsNothing);

      // And from the middle: ending does not move the reader either.
      await scrollUp(tester, 500);
      final middle = controller.offset;
      segments = [...segments, _stored(43)];
      await pump(tester, live: false);
      expect(controller.offset, closeTo(middle, 0.5));
    });

    testWidgets('a follow switched back on does not pull a reader who is mid-list', (tester) async {
      await pump(tester);
      await scrollUp(tester);
      final held = controller.offset;

      // Choosing lines or playing one switches the follow off, then on again.
      follow = false;
      await pump(tester);
      follow = true;
      await pump(tester);
      liveLines.value = 10;
      await tester.pumpAndSettle();

      expect(controller.offset, closeTo(held, 0.5));
      expect(find.byKey(_jump), findsOneWidget);
    });

    testWidgets('a follow switched back on resumes for a reader who is at the end', (tester) async {
      await pump(tester);

      follow = false;
      await pump(tester);
      follow = true;
      await pump(tester);
      liveLines.value = 10;
      await tester.pumpAndSettle();

      expectAtEnd();
    });

    testWidgets('with reduced motion the jump button places the list at the end without animating', (tester) async {
      await pump(tester, reducedMotion: true);
      await scrollUp(tester);

      await tester.tap(find.byKey(_jump));
      for (var frame = 0; frame < 6; frame++) {
        await tester.pump();
      }

      expectAtEnd();
    });

    testWidgets('a saved conversation still opens at its first line', (tester) async {
      follow = false;
      await pump(tester, live: false);

      expect(controller.offset, 0);
      expect(find.byKey(_jump), findsNothing);
    });
  });

  group('the Transcript tab', () {
    ServerConversation conversation({required bool live}) => ServerConversation.fromJson({
          'id': 'open',
          'created_at': DateTime.utc(2026, 11, 25, 0, 36).toIso8601String(),
          'started_at': DateTime.utc(2026, 11, 25, 0, 36).toIso8601String(),
          'finished_at': DateTime.utc(2026, 11, 25, 0, 46).toIso8601String(),
          'source': 'omi',
          'status': live ? 'in_progress' : 'completed',
          'structured': {'title': 'Planning', 'overview': '', 'emoji': '🗓️'},
          'transcript_segments': [
            for (var i = 0; i < 40; i++)
              {
                'id': 's$i',
                'text': 'Stored line $i with enough words to fill a row of the transcript.',
                'start': i * 10.0,
                'end': i * 10.0 + 5,
                'is_user': i.isEven,
              },
          ],
          'kind': 'conversation',
          'tile_state': live ? 'live' : 'closed',
          'v3_recording_ids': ['uploaded-1'],
        });

    Future<ConversationDetailProvider> pumpTab(WidgetTester tester,
        {required bool live, required bool v3, void Function(TranscriptSegment)? onSegmentTap}) async {
      final row = conversation(live: live);
      final detail = ConversationDetailProvider(fetchConversation: (_) async => row)..selectedDate = row.createdAt;
      detail.setCachedConversation(row);
      final accounts = ConversationsV3Provider(
          uid: () => 'owner-1',
          cached: v3 ? 'owner-1:1' : null,
          fetchLive: () async => ApiSuccess(ConversationsLiveRead(v3: v3, conversation: null)));
      addTearDown(accounts.dispose);
      await accounts.refresh();
      final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []));
      final outcome = SpeakerTagOutcomeController(
          fetchPerson: (_) async =>
              ApiSuccess(Person(id: 'p', name: 'P', createdAt: DateTime(2026), updatedAt: DateTime(2026))),
          fetchMatches: (_) async => const ApiSuccess([]));
      await tester.pumpWidget(MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: detail),
            ChangeNotifierProvider.value(value: accounts),
            ChangeNotifierProvider.value(value: people),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider.value(value: outcome),
          ],
          child: MaterialApp(
              theme: buildOmiTheme(brightness: Brightness.dark),
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: Scaffold(body: TranscriptWidgets(onSegmentTap: onSegmentTap)))));
      await tester.pumpAndSettle();
      return detail;
    }

    ScrollPosition position(WidgetTester tester) => tester.state<ScrollableState>(find.byType(Scrollable)).position;

    testWidgets('a conversation in progress opens at its newest line and follows it', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
      await SharedPreferencesUtil.init();
      await pumpTab(tester, live: true, v3: true);

      final list = tester.widget<TranscriptWidget>(find.byType(TranscriptWidget));
      expect(list.followLatest, isTrue);
      // The jump button sits above the page's floating bar and its fade.
      expect(list.jumpToLatestButtonBottom, greaterThanOrEqualTo(32 + 56 + 28));
      expect(position(tester).pixels, closeTo(position(tester).maxScrollExtent, 0.5));
      expect(position(tester).maxScrollExtent, greaterThan(500));
    });

    double footer(WidgetTester tester) =>
        tester.getSize(find.byKey(const ValueKey('transcript_bottom_spacing'))).height;

    testWidgets('while in progress the newest line sits just above the floating bar', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
      await SharedPreferencesUtil.init();
      final detail = await pumpTab(tester, live: true, v3: true);

      // The bar reaches 32 + 56 points up from the screen edge and the page fades 28 more above it.
      expect(footer(tester), greaterThanOrEqualTo(32 + 56 + 28 + 8));
      expect(footer(tester), lessThan(160));
      final held = position(tester).pixels;

      // Ended: the saved conversation's roomier foot comes back under the reader without moving them.
      detail.setCachedConversation(conversation(live: false));
      detail.notifyListeners();
      await tester.pumpAndSettle();
      expect(footer(tester), 270);
      expect(position(tester).pixels, closeTo(held, 0.5));
    });

    testWidgets('once it has ended the transcript stays put and no longer follows', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
      await SharedPreferencesUtil.init();
      final detail = await pumpTab(tester, live: true, v3: true);
      final held = position(tester).pixels;

      detail.setCachedConversation(conversation(live: false));
      detail.notifyListeners();
      await tester.pumpAndSettle();

      expect(tester.widget<TranscriptWidget>(find.byType(TranscriptWidget)).followLatest, isFalse);
      expect(position(tester).pixels, closeTo(held, 0.5));
      expect(find.byKey(_jump), findsNothing);
    });

    testWidgets('no_live_player: a line tap seeks nothing while in progress, and seeks again once ended',
        (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
      await SharedPreferencesUtil.init();
      addTearDown(() => ReliabilityExperiments.overrideForTesting(null));
      TranscriptWidget list() => tester.widget<TranscriptWidget>(find.byType(TranscriptWidget));

      final detail = await pumpTab(tester, live: true, v3: true, onSegmentTap: (_) {});
      expect(list().onSegmentTap, isNotNull, reason: 'off: a line tap plays from that line');

      ReliabilityExperiments.overrideForTesting({'no_live_player'});
      detail.notifyListeners();
      await tester.pumpAndSettle();
      expect(list().onSegmentTap, isNull);
      expect(list().followLatest, isTrue);

      detail.setCachedConversation(conversation(live: false));
      detail.notifyListeners();
      await tester.pumpAndSettle();
      expect(list().onSegmentTap, isNotNull);
    });

    testWidgets('a saved conversation opens at its first line', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
      await SharedPreferencesUtil.init();
      await pumpTab(tester, live: false, v3: true);

      expect(tester.widget<TranscriptWidget>(find.byType(TranscriptWidget)).followLatest, isFalse);
      expect(position(tester).pixels, 0);
    });
  });
}
