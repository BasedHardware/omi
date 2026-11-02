import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/audio/partial_audio_coverage.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

final _start = DateTime.utc(2026, 10, 2, 14, 0);

/// A conversation whose transcript spans [spokenSeconds] with one stored file of [savedSeconds].
ServerConversation _conversation({required double spokenSeconds, required double savedSeconds}) {
  return ServerConversation(
    id: 'conv-partial',
    createdAt: _start,
    startedAt: _start,
    structured: Structured('Phone call', ''),
    transcriptSegments: [
      TranscriptSegment(
        id: 's-0',
        text: 'hello',
        speaker: 'SPEAKER_0',
        isUser: false,
        personId: null,
        start: 0,
        end: 5,
        translations: [],
      ),
      TranscriptSegment(
        id: 's-1',
        text: 'bye',
        speaker: 'SPEAKER_1',
        isUser: false,
        personId: null,
        start: spokenSeconds - 5,
        end: spokenSeconds,
        translations: [],
      ),
    ],
    audioFiles: [
      AudioFile(
        id: 'a-1',
        uid: 'u',
        conversationId: 'conv-partial',
        chunkTimestamps: const [],
        duration: savedSeconds,
        startedAt: _start,
      ),
    ],
  );
}

Future<void> _pumpBar(WidgetTester tester, ServerConversation conversation) async {
  final provider = ConversationDetailProvider()
    ..selectedDate = conversationLocalDayKey(conversation.createdAt)
    ..setCachedConversation(conversation);
  addTearDown(provider.dispose);
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: ChangeNotifierProvider<ConversationDetailProvider>.value(
        value: provider,
        child: Scaffold(
          body: ConversationBottomBar(
            mode: ConversationBottomBarMode.detail,
            selectedTab: ConversationTab.transcript,
            onTabSelected: (_) {},
            onStopPressed: () {},
            hasSegments: true,
            conversation: conversation,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  group('savedAudioIsPartial', () {
    test('a few seconds of audio under a minutes-long transcript is partial', () {
      expect(savedAudioIsPartial(savedSeconds: 3, conversationSeconds: 349), isTrue);
      expect(savedAudioIsPartial(savedSeconds: 80, conversationSeconds: 100), isTrue);
    });

    test('audio that covers the conversation, give or take a few seconds, is not', () {
      expect(savedAudioIsPartial(savedSeconds: 349, conversationSeconds: 349), isFalse);
      expect(savedAudioIsPartial(savedSeconds: 341, conversationSeconds: 349), isFalse,
          reason: 'under the 10 s shortfall floor');
      expect(savedAudioIsPartial(savedSeconds: 95, conversationSeconds: 100), isFalse,
          reason: 'within the 90% coverage band');
      expect(savedAudioIsPartial(savedSeconds: 360, conversationSeconds: 349), isFalse,
          reason: 'audio longer than the transcript is never partial');
    });

    test('nothing saved or nothing spoken is not a partial recording', () {
      expect(savedAudioIsPartial(savedSeconds: 0, conversationSeconds: 349), isFalse);
      expect(savedAudioIsPartial(savedSeconds: 3, conversationSeconds: 0), isFalse);
      expect(savedAudioIsPartial(savedSeconds: double.nan, conversationSeconds: 349), isFalse);
    });
  });

  group('player label', () {
    testWidgets('says how much of the conversation was saved when the audio is far shorter (#19243)', (tester) async {
      await _pumpBar(tester, _conversation(spokenSeconds: 349, savedSeconds: 3));

      expect(find.text('0:03 of 5:49 audio saved'), findsOneWidget);
      expect(find.text('-0:03'), findsNothing, reason: 'the bare length reads as a broken recording');
      expect(find.bySemanticsLabel('Play'), findsOneWidget, reason: 'the short clip still plays');
      expect(tester.takeException(), isNull);
    });

    testWidgets('keeps the remaining-time label when the audio covers the conversation', (tester) async {
      await _pumpBar(tester, _conversation(spokenSeconds: 349, savedSeconds: 349));

      expect(find.text('-5:49'), findsOneWidget);
      expect(find.textContaining('audio saved'), findsNothing);
    });
  });
}
