import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/widgets/transcript.dart';

void main() {
  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
  });

  TranscriptSegment _segment(String id, int speakerId) {
    return TranscriptSegment(
      id: id,
      text: 'Hello world',
      speaker: 'SPEAKER_0$speakerId',
      speakerId: speakerId,
      isUser: false,
      personId: null,
      start: 0.0,
      end: 1.0,
      translations: [],
    );
  }

  group('Tag button visibility', () {
    testWidgets('Tag is hidden in live capture (isConversationDetail=false)', (tester) async {
      final segment = _segment('seg1', 1);
      final suggestion = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person-123',
        personName: 'Alice',
        segmentId: 'seg1',
      );

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: false, // Live capture mode
            suggestions: {'seg1': suggestion},
          ),
        ),
      ));

      // Tag should NOT be visible in live capture
      expect(find.text('Tag'), findsNothing);
    });

    testWidgets('Tag is visible in conversation detail (isConversationDetail=true)', (tester) async {
      final segment = _segment('seg2', 1);
      final suggestion = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person-456',
        personName: 'Bob',
        segmentId: 'seg2',
      );

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: true, // Conversation detail mode
            suggestions: {'seg2': suggestion},
          ),
        ),
      ));

      // Tag SHOULD be visible in conversation detail
      expect(find.text('Tag'), findsOneWidget);
    });

    testWidgets('Tag is not shown when no suggestion exists', (tester) async {
      final segment = _segment('seg3', 1);

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: true,
            suggestions: {}, // No suggestions
          ),
        ),
      ));

      // Tag should not be visible without suggestions
      expect(find.text('Tag'), findsNothing);
    });

    testWidgets('Tag is not shown when person is already assigned', (tester) async {
      final segment = TranscriptSegment(
        id: 'seg4',
        text: 'Hello',
        speaker: 'SPEAKER_01',
        speakerId: 1,
        isUser: false,
        personId: 'already-assigned-person', // Person already assigned
        start: 0.0,
        end: 1.0,
        translations: [],
      );
      final suggestion = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'new-person',
        personName: 'NewPerson',
        segmentId: 'seg4',
      );

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TranscriptWidget(
            segments: [segment],
            isConversationDetail: true,
            suggestions: {'seg4': suggestion},
          ),
        ),
      ));

      // Tag should not be visible when person is already assigned
      // (the condition is suggestion != null && person == null)
      expect(find.text('Tag'), findsNothing);
    });
  });
}
