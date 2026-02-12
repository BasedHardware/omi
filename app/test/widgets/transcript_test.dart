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

  TranscriptSegment _segment(String id, int speakerId) {
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
      await setupSharedPreferences(cachedPeople: [
        {
          'id': 'person-123',
          'name': 'Alice',
          'created_at': now.toUtc().toIso8601String(),
          'updated_at': now.toUtc().toIso8601String(),
        }
      ]);

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

      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: false,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Should show person name
      expect(find.text('Alice'), findsOneWidget);
      expect(find.text('Speaker 2'), findsNothing);
    });

    testWidgets('shows Speaker X when no person is assigned', (tester) async {
      final segment = _segment('seg2', 0);

      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: false,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Should show Speaker X fallback
      expect(find.text('Speaker 1'), findsOneWidget);
    });

    testWidgets('Tag button is removed from UI', (tester) async {
      final segment = _segment('seg3', 1);
      final suggestion = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person-456',
        personName: 'Bob',
        segmentId: 'seg3',
      );

      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: true,
            suggestions: {'seg3': suggestion},
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Tag button should no longer exist
      expect(find.text('Tag'), findsNothing);
    });
  });
}
