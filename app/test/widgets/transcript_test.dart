import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/widgets/transcript.dart';

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

    testWidgets('Tag button is removed from UI', (tester) async {
      final segment = segmentFor('seg3', 1);
      final suggestion = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person-456',
        personName: 'Bob',
        segmentId: 'seg3',
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
          home: Scaffold(
            body: TranscriptWidget(segments: [segment], isConversationDetail: true, suggestions: {'seg3': suggestion}),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tag button should no longer exist
      expect(find.text('Tag'), findsNothing);
    });
  });

  group('Live transcript scrolling', () {
    late ScrollController controller;
    late TranscriptScrollState scrollState;
    late List<TranscriptSegment> segments;

    Future<void> pumpTranscript(WidgetTester tester) async {
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
                segments: segments,
                bottomMargin: 0,
                followLatest: true,
                scrollState: scrollState,
                jumpToLatestButtonBottom: 84,
                onScrollControllerReady: (value) => controller = value,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    setUp(() {
      scrollState = TranscriptScrollState();
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

    testWidgets('a user position away from the bottom survives reopening', (tester) async {
      await pumpTranscript(tester);
      await tester.drag(find.byType(ListView), const Offset(0, 260));
      await tester.pumpAndSettle();

      final preservedOffset = controller.offset;
      expect(scrollState.isAtBottom, isFalse);
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await pumpTranscript(tester);

      expect(controller.offset, closeTo(preservedOffset, 0.1));
      expect(find.byKey(const ValueKey('transcript_jump_to_latest')), findsOneWidget);
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

    testWidgets('live controls reserve only the standard 120 point footer', (tester) async {
      await pumpTranscript(tester);

      final footer = tester.widget<SizedBox>(find.byKey(const ValueKey('transcript_bottom_spacing')));
      expect(footer.height, 120);
    });
  });
}
