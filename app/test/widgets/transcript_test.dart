import 'dart:convert';

import 'package:flutter/gestures.dart' show kDoubleTapTimeout;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/components/omi_spinner.dart';
import 'package:omi/widgets/speaker_label_badge.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:provider/provider.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  /// Helper to reset SharedPreferences with optional cached people
  Future<void> setupSharedPreferences({List<Map<String, dynamic>>? cachedPeople}) async {
    final values = <String, Object>{};
    if (cachedPeople != null) {
      values['cachedPeople'] = cachedPeople.map((p) => jsonEncode(p)).toList();
    }
    SharedPreferences.setMockInitialValues(values);
    await SharedPreferencesUtil.init();
  }

  TranscriptSegment segmentFor(String id, int speakerId) {
    // Note: speakerId is extracted from speaker string by TranscriptSegment constructor
    return TranscriptSegment(
      id: id,
      text: 'Hello world',
      speaker: 'SPEAKER_0$speakerId',
      isUser: false,
      personId: null,
      start: 0.0,
      end: 1.0,
      translations: [],
    );
  }

  testWidgets('mounted transcript follows people refresh, rename, and account clear', (tester) async {
    await setupSharedPreferences();
    var loaded = <Person>[];
    final people = PeopleProvider(
      loadPeople: () async => PeopleListResponse(people: loaded),
      renamePerson: (_, __) async => true,
    );
    final segment = segmentFor('reactive', 2)..personId = 'later';
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: people,
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidget(segments: [segment])),
        ),
      ),
    );
    await tester.pumpAndSettle();
    // SPEAKER_02 is the conversation's only anonymous speaker, so it reads "Speaker 1" (dense numbering).
    expect(find.text('Speaker 1'), findsOneWidget);
    loaded = [Person(id: 'later', name: 'Alex', createdAt: DateTime(2026), updatedAt: DateTime(2026))];
    await people.setPeople();
    await tester.pumpAndSettle();
    expect(find.text('Alex'), findsOneWidget);
    await people.updatePersonProvider(people.people.single, 'Sam');
    await tester.pumpAndSettle();
    expect(find.text('Sam'), findsOneWidget);
    expect(find.text('Alex'), findsNothing);
    people.clearUserData();
    await tester.pumpAndSettle();
    expect(find.text('Sam'), findsNothing);
    // SPEAKER_02 is the conversation's only anonymous speaker, so it reads "Speaker 1" (dense numbering).
    expect(find.text('Speaker 1'), findsOneWidget);
  });

  group('Speaker label display', () {
    testWidgets('shows person name when personId is set and in cache', (tester) async {
      final now = DateTime.now();
      await setupSharedPreferences(
        cachedPeople: [
          {
            'id': 'person-123',
            'name': 'Alice',
            'created_at': now.toUtc().toIso8601String(),
            'updated_at': now.toUtc().toIso8601String(),
          },
        ],
      );

      final segment = TranscriptSegment(
        id: 'seg1',
        text: 'Hello world',
        speaker: 'SPEAKER_01',
        isUser: false,
        personId: 'person-123',
        start: 0.0,
        end: 1.0,
        translations: [],
      );

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidget(segments: [segment], isConversationDetail: false)),
        ),
      );
      await tester.pumpAndSettle();

      // Should show person name
      expect(find.text('Alice'), findsOneWidget);
      expect(find.text('Speaker 2'), findsNothing);
    });

    testWidgets('shows Speaker X when no person is assigned', (tester) async {
      final segment = segmentFor('seg2', 0);

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidget(segments: [segment], isConversationDetail: false)),
        ),
      );
      await tester.pumpAndSettle();

      // Should show Speaker X fallback
      expect(find.text('Speaker 1'), findsOneWidget);
    });

    testWidgets('unavailable resolution does not render chunk ids as distinct people', (tester) async {
      final segments = [segmentFor('first', 27), segmentFor('second', 28)];
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidget(segments: segments, unresolvedSpeakers: true)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Speaker'), findsNWidgets(2));
      expect(find.text('Speaker ?'), findsNothing);
      expect(find.text('Speaker 1'), findsNothing);
      expect(find.text('Speaker 2'), findsNothing);
    });

    testWidgets('Tag button is removed from UI', (tester) async {
      final segment = segmentFor('seg3', 1);

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: TranscriptWidget(segments: [segment], isConversationDetail: true)),
        ),
      );
      await tester.pumpAndSettle();

      // Tag button should no longer exist
      expect(find.text('Tag'), findsNothing);
    });
  });

  group('Saved conversation lines', () {
    testWidgets('name and clock time sit over the words, with no bubble or avatar', (tester) async {
      await setupSharedPreferences();
      final mine = TranscriptSegment(
        id: 'mine',
        text: 'We ship the widgets first.',
        speaker: 'SPEAKER_00',
        isUser: true,
        personId: null,
        start: 0,
        end: 2,
        translations: [],
      );
      final theirs = TranscriptSegment(
        id: 'theirs',
        text: 'Agreed, chat can follow.',
        speaker: 'SPEAKER_01',
        isUser: false,
        personId: null,
        start: 65,
        end: 67,
        translations: [],
      );
      final named = <(String, int)>[];
      final played = <String>[];
      final edited = <int>[];

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: TranscriptWidget(
              segments: [mine, theirs],
              isConversationDetail: true,
              startedAt: DateTime(2026, 9, 30, 12, 40),
              editSegment: (id, speakerId) => named.add((id, speakerId)),
              onSegmentTap: (segment) => played.add(segment.id),
              onEditSegmentText: edited.add,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('You'), findsOneWidget);
      expect(find.text('Speaker 1'), findsOneWidget);
      // The wall clock (start + offset), not "0:00" / "1:05"; intl may put a narrow space before PM.
      expect(find.textContaining(RegExp(r'^12:40\sPM$')), findsOneWidget);
      expect(find.textContaining(RegExp(r'^12:41\sPM$')), findsOneWidget);
      expect(find.byType(CircleAvatar), findsNothing);

      // Only a voice nobody has named is underlined.
      final unnamed = tester.widget<Text>(find.text('Speaker 1'));
      expect(unnamed.style?.decoration, TextDecoration.underline);
      expect(unnamed.style?.decorationStyle, TextDecorationStyle.dotted);
      expect(tester.widget<Text>(find.text('You')).style?.decoration, isNull);

      await tester.tap(find.text('Speaker 1'));
      expect(named, [('theirs', 1)]);
      expect(played, isEmpty);

      // Tapping the words plays from that line; so does the rest of the line (the time).
      // A single tap waits out the double-tap window (double-tap edits).
      await tester.tap(find.text('We ship the widgets first.', findRichText: true));
      await tester.pump(kDoubleTapTimeout + const Duration(milliseconds: 50));
      await tester.tap(find.textContaining(RegExp(r'^12:41')));
      await tester.pump(kDoubleTapTimeout + const Duration(milliseconds: 50));
      expect(played, ['mine', 'theirs']);

      final words = find.text('Agreed, chat can follow.', findRichText: true);
      await tester.tap(words);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(words);
      await tester.pumpAndSettle();
      expect(edited, [1]);
      expect(played, ['mine', 'theirs']);
    });

    testWidgets('a long saved transcript opens at its first line and stays there when it changes', (tester) async {
      await setupSharedPreferences();
      List<TranscriptSegment> lines(int count) => [
            for (var i = 0; i < count; i++)
              TranscriptSegment(
                id: 'line-$i',
                text: 'Line number $i of the conversation.',
                speaker: 'SPEAKER_0${i % 2}',
                isUser: i.isEven,
                personId: null,
                start: i * 10.0,
                end: i * 10.0 + 5,
                translations: [],
              ),
          ];
      Widget page(List<TranscriptSegment> segments) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: TranscriptWidget(segments: segments, isConversationDetail: true)),
          );

      await tester.pumpWidget(page(lines(60)));
      await tester.pumpAndSettle();
      expect(find.text('Line number 0 of the conversation.', findRichText: true).hitTestable(), findsOneWidget);
      expect(find.text('Line number 59 of the conversation.', findRichText: true), findsNothing);

      await tester.pumpWidget(page(lines(61)));
      await tester.pumpAndSettle();
      expect(find.text('Line number 0 of the conversation.', findRichText: true).hitTestable(), findsOneWidget);
    });
  });

  test('a transcript scroll-state store resets on a fresh page but reuses a live session', () {
    final store = TranscriptScrollStateStore();
    final first = store.forSession('live-session');
    first.update(offset: 120, isAtBottom: false);

    expect(store.forSession('live-session'), same(first));
    expect(store.forSession('live-session').isAtBottom, isFalse);

    final nextSession = store.forSession('next-session');
    expect(nextSession, isNot(same(first)));
    expect(nextSession.hasPosition, isFalse);

    final freshPageStore = TranscriptScrollStateStore();
    expect(freshPageStore.forSession('live-session').hasPosition, isFalse);
  });

  group('Live transcript scrolling', () {
    late ScrollController controller;
    late TranscriptScrollState scrollState;
    late List<TranscriptSegment> segments;
    late int contentVersion;
    late String layoutIdentity;
    late List<Widget> leadingItems;
    late List<String> leadingItemIds;

    Future<void> pumpTranscript(WidgetTester tester, {bool settle = true}) async {
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: SizedBox(
              height: 320,
              child: TranscriptWidget(
                key: const ValueKey('live-transcript-test-session'),
                segments: segments,
                bottomMargin: 0,
                followLatest: true,
                scrollState: scrollState,
                jumpToLatestButtonBottom: 84,
                onScrollControllerReady: (value) => controller = value,
                contentVersion: contentVersion,
                layoutIdentity: layoutIdentity,
                leadingItems: leadingItems,
                leadingItemIds: leadingItemIds,
              ),
            ),
          ),
        ),
      );
      if (settle) await tester.pumpAndSettle();
    }

    setUp(() {
      scrollState = TranscriptScrollState();
      contentVersion = 0;
      layoutIdentity = 'transcript';
      leadingItems = [];
      leadingItemIds = [];
      segments = List.generate(
        30,
        (index) => TranscriptSegment(
          id: 'live-$index',
          text: 'Transcript segment $index with enough words to make this a long conversation.',
          speaker: 'SPEAKER_0${index % 2}',
          isUser: false,
          personId: null,
          start: index.toDouble(),
          end: index + 1.0,
          translations: const [],
        ),
      );
    });

    testWidgets('a fresh long transcript opens at the latest segment', (tester) async {
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(controller.position.maxScrollExtent, 0.1));
      expect(scrollState.isAtBottom, isTrue);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsNothing);
    });

    testWidgets('a fresh transcript load starts at the latest segment', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      scrollState = TranscriptScrollState();
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(controller.position.maxScrollExtent, 0.1));
      expect(scrollState.isAtBottom, isTrue);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsNothing);
    });

    testWidgets('the jump control animates to the latest segment and hides', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('transcript_jump_to_latest')));
      await tester.pumpAndSettle();

      expect(controller.offset, closeTo(controller.position.maxScrollExtent, 0.1));
      expect(scrollState.isAtBottom, isTrue);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsNothing);
    });

    testWidgets('manual scrolling up stays put while live transcript grows', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      final preservedOffset = controller.offset;
      expect(scrollState.isAtBottom, isFalse);

      segments = [
        ...segments,
        TranscriptSegment(
          id: 'live-new',
          text: List.filled(80, 'new live words').join(' '),
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: segments.length.toDouble(),
          end: segments.length + 1.0,
          translations: const [],
        ),
      ];
      contentVersion++;
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(preservedOffset, 0.1));
      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);
    });

    testWidgets('manual scrolling up stays put when live content arrives mid-gesture', (tester) async {
      await pumpTranscript(tester);
      final gestureStart = tester.getCenter(find.byType(ListView));
      final gesture = await tester.startGesture(gestureStart);
      for (var step = 0; step < 5; step++) {
        await gesture.moveBy(const Offset(0, 52));
        await tester.pump(const Duration(milliseconds: 10));
      }
      await tester.pump();

      final preservedOffset = controller.offset;
      segments = [
        ...segments,
        TranscriptSegment(
          id: 'live-mid-gesture',
          text: List.filled(80, 'new live words').join(' '),
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: segments.length.toDouble(),
          end: segments.length + 1.0,
          translations: const [],
        ),
      ];
      contentVersion++;
      await pumpTranscript(tester, settle: false);
      await tester.pump(const Duration(milliseconds: 16));

      expect(controller.offset, closeTo(preservedOffset, 0.1));
      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);

      await gesture.up();
      await tester.pumpAndSettle();
    });

    testWidgets('a drag started during an in-flight live follow wins and never re-pins', (tester) async {
      await pumpTranscript(tester);

      // A live tick starts the 500ms follow animation toward the new edge.
      segments = [
        ...segments,
        TranscriptSegment(
          id: 'live-follow-race',
          text: List.filled(80, 'new live words').join(' '),
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: segments.length.toDouble(),
          end: segments.length + 1.0,
          translations: const [],
        ),
      ];
      contentVersion++;
      await pumpTranscript(tester, settle: false);
      // Leave the follow mid-flight: the first 500ms pass is still animating.
      await tester.pump(const Duration(milliseconds: 490));

      // The reader starts dragging up slowly from the live edge. The first
      // pixels stay inside the at-bottom band where a lost gesture used to be
      // forgotten and re-pinned by the next live tick.
      final gesture = await tester.startGesture(tester.getCenter(find.byType(ListView)));
      for (var step = 0; step < 3; step++) {
        await gesture.moveBy(const Offset(0, 12));
        await tester.pump(const Duration(milliseconds: 40));
      }

      // Another live tick lands while the gesture is still active.
      segments = [
        ...segments,
        TranscriptSegment(
          id: 'live-follow-race-2',
          text: List.filled(80, 'more live words').join(' '),
          speaker: 'SPEAKER_01',
          isUser: false,
          personId: null,
          start: segments.length.toDouble(),
          end: segments.length + 1.0,
          translations: const [],
        ),
      ];
      contentVersion++;
      await pumpTranscript(tester, settle: false);
      await tester.pump(const Duration(milliseconds: 40));

      for (var step = 0; step < 4; step++) {
        await gesture.moveBy(const Offset(0, 20));
        await tester.pump(const Duration(milliseconds: 40));
      }

      // The drag owns the position: it stays away from the live edge instead
      // of being yanked back by the competing follow.
      expect(controller.position.maxScrollExtent - controller.offset, greaterThan(48));
      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);

      await gesture.up();
      await tester.pumpAndSettle();

      // Completing the gesture must not re-pin to the live edge.
      expect(controller.position.maxScrollExtent - controller.offset, greaterThan(48));
      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);
    });

    testWidgets('same-ID growth of the live segment holds an unfollowed reading position', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      final preservedOffset = controller.offset;
      expect(scrollState.isAtBottom, isFalse);

      final last = segments.last;
      segments = [
        ...segments.take(segments.length - 1),
        TranscriptSegment(
          id: last.id,
          text: List.filled(80, 'revised live tail text').join(' '),
          speaker: last.speaker,
          isUser: last.isUser,
          personId: last.personId,
          start: last.start,
          end: last.end,
          translations: const [],
        ),
      ];
      contentVersion++;
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(preservedOffset, 0.1));
      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);
    });

    testWidgets('same-ID transcript growth keeps following the live edge', (tester) async {
      await pumpTranscript(tester);

      final last = segments.last;
      segments = [
        ...segments.take(segments.length - 1),
        TranscriptSegment(
          id: last.id,
          text: List.filled(80, 'revised transcript text').join(' '),
          speaker: last.speaker,
          isUser: last.isUser,
          personId: last.personId,
          start: last.start,
          end: last.end,
          translations: const [],
        ),
      ];
      contentVersion++;
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(controller.position.maxScrollExtent, 0.1));
      expect(scrollState.isAtBottom, isTrue);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsNothing);
    });

    testWidgets('growth inside an existing photo group keeps following the live edge', (tester) async {
      layoutIdentity = 'photo-timeline';
      leadingItemIds = ['photo-group-1'];
      leadingItems = const [SizedBox(height: 80)];
      await pumpTranscript(tester);

      leadingItems = const [SizedBox(height: 280)];
      contentVersion++;
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(controller.position.maxScrollExtent, 0.1));
      expect(scrollState.isAtBottom, isTrue);
    });

    testWidgets('overlapping live updates coalesce into one settled bottom follow', (tester) async {
      await pumpTranscript(tester);

      for (var update = 0; update < 3; update++) {
        segments = [
          ...segments,
          TranscriptSegment(
            id: 'overlap-$update',
            text: List.filled(12, 'new live words').join(' '),
            speaker: 'SPEAKER_00',
            isUser: false,
            personId: null,
            start: segments.length.toDouble(),
            end: segments.length + 1.0,
            translations: const [],
          ),
        ];
        contentVersion++;
        await pumpTranscript(tester, settle: false);
        await tester.pump(const Duration(milliseconds: 40));
      }
      await tester.pumpAndSettle();

      expect(controller.offset, closeTo(controller.position.maxScrollExtent, 0.1));
      expect(scrollState.isAtBottom, isTrue);
    });

    testWidgets('layout changes restore the same transcript anchor instead of a raw offset', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      final anchorId = scrollState.anchorSegmentId;
      expect(anchorId, isNotNull);
      final anchorFinder = find.byKey(ValueKey('transcript-segment-$anchorId'));
      final anchorTop = tester.getTopLeft(anchorFinder).dy - tester.getTopLeft(find.byType(ListView)).dy;
      expect(scrollState.anchorViewportOffset, closeTo(anchorTop, 5));

      layoutIdentity = 'photo-timeline';
      leadingItemIds = ['new-photo-group'];
      leadingItems = const [SizedBox(height: 240)];
      contentVersion++;
      await pumpTranscript(tester);

      expect(scrollState.anchorSegmentId, anchorId);
      final restoredTop = tester.getTopLeft(anchorFinder).dy - tester.getTopLeft(find.byType(ListView)).dy;
      // Sliver layout may round the restored edge by the four-point separator,
      // but it must keep the same segment at the same reading position.
      expect(restoredTop, closeTo(anchorTop, 5));
      expect(scrollState.isAtBottom, isFalse);
    });

    testWidgets('deleting the first segment preserves a later reading anchor', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      final anchorId = scrollState.anchorSegmentId;
      expect(anchorId, isNotNull);
      final anchorFinder = find.byKey(ValueKey('transcript-segment-$anchorId'));
      final anchorTop = tester.getTopLeft(anchorFinder).dy - tester.getTopLeft(find.byType(ListView)).dy;
      expect(scrollState.anchorViewportOffset, closeTo(anchorTop, 5));

      segments = segments.skip(1).toList();
      contentVersion++;
      await pumpTranscript(tester);

      expect(scrollState.anchorSegmentId, anchorId);
      final restoredTop = tester.getTopLeft(anchorFinder).dy - tester.getTopLeft(find.byType(ListView)).dy;
      // Sliver layout may round the restored edge by the four-point separator,
      // but it must keep the same segment at the same reading position.
      expect(restoredTop, closeTo(anchorTop, 5));
      expect(scrollState.isAtBottom, isFalse);
    });

    testWidgets('live controls reserve only the standard 120 point footer', (tester) async {
      await pumpTranscript(tester);

      final footer = tester.widget<SizedBox>(find.byKey(const ValueKey('transcript_bottom_spacing')));
      expect(footer.height, 120);
    });
  });

  group('Saved detail lines from one voice', () {
    TranscriptSegment line(
      String id,
      int speakerId,
      String text,
      double start, {
      bool isUser = false,
      String? personId,
      String? source,
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
          speakerLabelSource: source,
        );

    List<TranscriptSegment> voicesFixture() => [
          line('a1', 3, 'First thing they said.', 0),
          line('a2', 3, 'Still the same voice.', 10),
          line('b1', 4, 'Another voice replies.', 20),
          line('a3', 3, 'The first voice again.', 30),
        ];

    Finder speakerNameLabels() =>
        find.byWidgetPredicate((widget) => widget is Text && RegExp(r'^Speaker(?: \?)?$').hasMatch(widget.data ?? ''));

    Future<void> pumpDetail(
      WidgetTester tester,
      List<TranscriptSegment> segments, {
      bool unresolved = false,
      List<String> tagging = const [],
      void Function(TranscriptSegment)? onSegmentTap,
      void Function(int)? onEditSegmentText,
      void Function(String, int)? editSegment,
      void Function(TranscriptSegment)? onConfirmSpeakerLabel,
      void Function(TranscriptSegment)? onRejectSpeakerLabel,
    }) =>
        tester.pumpWidget(
          MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(
              body: TranscriptWidget(
                segments: segments,
                isConversationDetail: true,
                unresolvedSpeakers: unresolved,
                taggingSegmentIds: tagging,
                onSegmentTap: onSegmentTap,
                onEditSegmentText: onEditSegmentText,
                editSegment: editSegment,
                onConfirmSpeakerLabel: onConfirmSpeakerLabel,
                onRejectSpeakerLabel: onRejectSpeakerLabel,
              ),
            ),
          ),
        );

    group('unresolved', () {
      testWidgets('render a name row once per turn, not once per line', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, voicesFixture(), unresolved: true);
        await tester.pumpAndSettle();

        expect(speakerNameLabels(), findsNWidgets(3));
      });

      testWidgets('name rows are the neutral "Speaker", never "Speaker ?" or a number', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, voicesFixture(), unresolved: true);
        await tester.pumpAndSettle();

        expect(find.text('Speaker'), findsNWidgets(3));
        expect(find.text('Speaker ?'), findsNothing);
        expect(find.text('Speaker 1'), findsNothing);
      });

      testWidgets('show the time where a turn starts, not on its continuation', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, voicesFixture(), unresolved: true);
        await tester.pumpAndSettle();

        expect(find.text('0:00'), findsOneWidget);
        expect(find.text('0:20'), findsOneWidget);
        expect(find.text('0:30'), findsOneWidget);
        expect(find.text('0:10'), findsNothing);
      });

      testWidgets('every line still seeks in order and double-tap edits without seeking', (tester) async {
        await setupSharedPreferences();
        final segments = voicesFixture();
        final played = <TranscriptSegment>[];
        final edited = <int>[];
        await pumpDetail(tester, segments, unresolved: true, onSegmentTap: played.add, onEditSegmentText: edited.add);
        await tester.pumpAndSettle();

        for (final segment in segments) {
          expect(find.byKey(ValueKey('transcript-segment-${segment.id}')), findsOneWidget);
          await tester.tap(find.text(segment.text, findRichText: true));
          await tester.pump(kDoubleTapTimeout + const Duration(milliseconds: 50));
        }
        expect(played, segments);
        expect(played.asMap().entries.every((entry) => identical(entry.value, segments[entry.key])), isTrue);

        final a2 = find.text('Still the same voice.', findRichText: true);
        await tester.tap(a2);
        await tester.pump(const Duration(milliseconds: 50));
        await tester.tap(a2);
        await tester.pumpAndSettle();
        expect(edited, [1]);
        expect(played, segments);
      });

      testWidgets('a continuation keeps selection area and long press does not seek or edit', (tester) async {
        await setupSharedPreferences();
        final played = <TranscriptSegment>[];
        final edited = <int>[];
        await pumpDetail(
          tester,
          voicesFixture(),
          unresolved: true,
          onSegmentTap: played.add,
          onEditSegmentText: edited.add,
        );
        await tester.pumpAndSettle();

        final words = find.text('Still the same voice.', findRichText: true);
        expect(find.ancestor(of: words, matching: find.byType(SelectionArea)), findsOneWidget);
        await tester.longPress(words);
        await tester.pump();
        await tester.pump(kDoubleTapTimeout);
        expect(played, isEmpty);
        expect(edited, isEmpty);
      });

      testWidgets('a continuation line keeps its tagging spinner without name or time', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, voicesFixture(), unresolved: true, tagging: ['a2']);
        for (var i = 0; i < 10; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }

        expect(find.byType(OmiSpinner), findsOneWidget);
        expect(speakerNameLabels(), findsNWidgets(3));
        expect(find.text('0:10'), findsNothing);
      });

      testWidgets('unresolved name rows carry the dotted underline affordance', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, voicesFixture(), unresolved: true);
        await tester.pumpAndSettle();

        final labels = tester.widgetList<Text>(speakerNameLabels()).toList();
        expect(labels, hasLength(3));
        expect(labels.every((label) => label.style?.decoration == TextDecoration.underline), isTrue);
      });

      testWidgets('tapping a turn-first label opens naming for that segment', (tester) async {
        await setupSharedPreferences();
        final tagged = <(String, int)>[];
        await pumpDetail(
          tester,
          voicesFixture(),
          unresolved: true,
          editSegment: (id, speakerId) => tagged.add((id, speakerId)),
        );
        await tester.pumpAndSettle();

        for (var i = 0; i < 3; i++) {
          await tester.tap(speakerNameLabels().at(i));
          await tester.pumpAndSettle();
        }
        expect(tagged, [('a1', 3), ('b1', 4), ('a3', 3)]);
      });
    });

    group('resolved', () {
      testWidgets('group consecutive lines of one voice into one name row', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, voicesFixture());
        await tester.pumpAndSettle();

        expect(find.text('Speaker 1'), findsNWidgets(2));
        expect(find.text('Speaker 2'), findsOneWidget);
        expect(find.text('0:00'), findsOneWidget);
        expect(find.text('0:20'), findsOneWidget);
        expect(find.text('0:30'), findsOneWidget);
        expect(find.text('0:10'), findsNothing);
      });

      testWidgets('consecutive owner lines group into one "You" row', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, [
          line('u1', 0, 'I start.', 0, isUser: true),
          line('u2', 0, 'I keep going.', 10, isUser: true),
        ]);
        await tester.pumpAndSettle();

        expect(find.text('You'), findsOneWidget);
        expect(find.text('0:10'), findsNothing);
      });

      testWidgets('a changed isUser or personId starts a new name row', (tester) async {
        final now = DateTime.now();
        await setupSharedPreferences(
          cachedPeople: [
            {
              'id': 'p1',
              'name': 'Ada',
              'created_at': now.toUtc().toIso8601String(),
              'updated_at': now.toUtc().toIso8601String(),
            },
            {
              'id': 'p2',
              'name': 'Ben',
              'created_at': now.toUtc().toIso8601String(),
              'updated_at': now.toUtc().toIso8601String(),
            },
          ],
        );
        await pumpDetail(tester, [line('own', 0, 'Mine.', 0, isUser: true), line('same-id-other', 0, 'Not me.', 10)]);
        await tester.pumpAndSettle();
        expect(find.text('You'), findsOneWidget);
        expect(find.text('Speaker 1'), findsOneWidget);

        await pumpDetail(tester, [
          line('ada', 5, 'Ada speaks.', 0, personId: 'p1', source: 'manual'),
          line('ben', 5, 'Ben speaks.', 10, personId: 'p2', source: 'manual'),
        ]);
        await tester.pumpAndSettle();
        expect(find.text('Ada'), findsOneWidget);
        expect(find.text('Ben'), findsOneWidget);
      });

      testWidgets('a changed label source alone does not start a new name row', (tester) async {
        final now = DateTime.now();
        await setupSharedPreferences(
          cachedPeople: [
            {
              'id': 'p1',
              'name': 'Ada',
              'created_at': now.toUtc().toIso8601String(),
              'updated_at': now.toUtc().toIso8601String(),
            },
          ],
        );
        await pumpDetail(tester, [
          line('a1', 5, 'First labelled line.', 0, personId: 'p1', source: 'manual'),
          line('a2', 5, 'Second labelled line.', 10, personId: 'p1', source: 'auto'),
        ]);
        await tester.pumpAndSettle();

        expect(find.text('Ada'), findsOneWidget);
      });

      testWidgets('a continuation keeps its likely-speaker confirmation on the first auto line', (tester) async {
        final now = DateTime.now();
        await setupSharedPreferences(
          cachedPeople: [
            {
              'id': 'p1',
              'name': 'Ada',
              'created_at': now.toUtc().toIso8601String(),
              'updated_at': now.toUtc().toIso8601String(),
            },
          ],
        );
        final segments = [
          line('m1', 5, 'Ada manual line.', 0, personId: 'p1', source: 'manual'),
          line('a2', 5, 'Ada auto line.', 10, personId: 'p1', source: 'auto'),
          line('a3', 5, 'Ada auto again.', 20, personId: 'p1', source: 'auto'),
        ];
        final confirmed = <TranscriptSegment>[];
        final rejected = <TranscriptSegment>[];
        final played = <TranscriptSegment>[];
        await pumpDetail(
          tester,
          segments,
          onConfirmSpeakerLabel: confirmed.add,
          onRejectSpeakerLabel: rejected.add,
          onSegmentTap: played.add,
        );
        await tester.pumpAndSettle();

        expect(find.text('Ada'), findsOneWidget);
        expect(find.text('0:00'), findsOneWidget);
        expect(find.text('0:10'), findsNothing);
        expect(find.text('0:20'), findsNothing);

        final confirmBadge = find.byType(SpeakerLikelyConfirm);
        expect(confirmBadge, findsOneWidget);
        expect(
          find.descendant(of: find.byKey(const ValueKey('transcript-segment-a2')), matching: confirmBadge),
          findsOneWidget,
        );

        await tester.tap(find.byKey(const Key('speaker_likely_yes')));
        await tester.pumpAndSettle();
        expect(confirmed, hasLength(1));
        expect(identical(confirmed.single, segments[1]), isTrue);

        await tester.tap(find.byKey(const Key('speaker_likely_not')));
        await tester.pumpAndSettle();
        expect(rejected, hasLength(1));
        expect(identical(rejected.single, segments[1]), isTrue);

        expect(played, isEmpty);
        for (final segment in segments) {
          expect(find.byKey(ValueKey('transcript-segment-${segment.id}')), findsOneWidget);
          expect(find.text(segment.text, findRichText: true), findsOneWidget);
        }
      });

      testWidgets('consecutive Omi lines do not group', (tester) async {
        await setupSharedPreferences();
        await pumpDetail(tester, [
          line('o1', omiSpeakerId, 'Omi first.', 0),
          line('o2', omiSpeakerId, 'Omi second.', 10),
        ]);
        await tester.pumpAndSettle();

        expect(find.text('Omi'), findsNWidgets(2));
        expect(find.text('0:00'), findsOneWidget);
        expect(find.text('0:10'), findsOneWidget);
      });
    });

    testWidgets('the live bubble transcript still names every line', (tester) async {
      await setupSharedPreferences();
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: TranscriptWidget(segments: [line('v1', 3, 'Bubble one.', 0), line('v2', 3, 'Bubble two.', 10)]),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Speaker 1'), findsNWidgets(2));
    });
  });
}
