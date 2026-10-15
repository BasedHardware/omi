import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart' show FaIcon;
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

ServerConversation _conversation({required List<AppResponse> appResults, bool withAudio = false}) {
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: Structured('Sprint sync', 'First-party overview.', emoji: '🧠'),
    appResults: appResults,
    audioFiles: [
      if (withAudio) AudioFile(id: 'a-1', uid: 'u', conversationId: 'conv-1', chunkTimestamps: [], duration: 840),
    ],
  );
}

TranscriptSegment _segment(double start, double end) => TranscriptSegment(
      id: 's-$start',
      text: 'words',
      speaker: 'SPEAKER_0',
      isUser: false,
      personId: null,
      start: start,
      end: end,
      translations: [],
    );

ConversationDetailProvider _provider(ServerConversation conversation) {
  final provider = ConversationDetailProvider();
  provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
  provider.setCachedConversation(conversation);
  return provider;
}

Future<void> _pumpBar(
  WidgetTester tester,
  ConversationDetailProvider provider, {
  ConversationTab selectedTab = ConversationTab.summary,
  VoidCallback? onAudioInteraction,
  VoidCallback? onAskOmi,
  void Function(Future<void> Function(double, double))? onSeekFunctionReady,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: ChangeNotifierProvider<ConversationDetailProvider>.value(
        value: provider,
        child: Scaffold(
          body: ConversationBottomBar(
            mode: ConversationBottomBarMode.detail,
            onAudioInteraction: onAudioInteraction,
            onAskOmi: onAskOmi,
            onSeekFunctionReady: onSeekFunctionReady,
            selectedTab: selectedTab,
            onTabSelected: (_) {},
            onStopPressed: () {},
            hasSegments: true,
            conversation: provider.conversation,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('one bar: Ask Omi alone on Summary and on a silent Transcript, centred, with no mic', (tester) async {
    final provider = _provider(_conversation(appResults: [AppResponse('Imported app output.')]));
    addTearDown(provider.dispose);
    var asked = 0;

    await _pumpBar(tester, provider, onAskOmi: () => asked++);
    final bar = find.byKey(const ValueKey('detail_ask_omi'));
    expect(bar, findsOneWidget);
    expect(find.text('Ask Omi'), findsOneWidget);
    expect(tester.getCenter(find.text('Ask Omi')).dx, moreOrLessEquals(tester.getCenter(bar).dx, epsilon: 1));
    expect(find.descendant(of: bar, matching: find.byType(FaIcon)), findsNothing,
        reason: 'no mic, no glyph: just the words');
    // The summarizing app is picked from the ⋯ menu now, not the bar.
    expect(find.text('Unknown App'), findsNothing);
    expect(find.bySemanticsLabel('Transcript'), findsNothing);
    await tester.tap(bar);
    expect(asked, 1);

    await _pumpBar(tester, provider, selectedTab: ConversationTab.transcript, onAskOmi: () => asked++);
    expect(find.byKey(const ValueKey('detail_audio_player')), findsNothing);
    expect(find.byKey(const ValueKey('detail_ask_omi')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Transcript with audio: the waveform player and a round Ask button share the bar', (tester) async {
    final provider = _provider(_conversation(appResults: [], withAudio: true));
    addTearDown(provider.dispose);
    var asked = 0;

    await _pumpBar(tester, provider, selectedTab: ConversationTab.transcript, onAskOmi: () => asked++);
    final player = find.byKey(const ValueKey('detail_audio_player'));
    final ask = find.byKey(const ValueKey('detail_ask_omi_round'));
    expect(player, findsOneWidget);
    expect(ask, findsOneWidget);
    expect(find.byKey(const ValueKey('detail_ask_omi')), findsNothing);
    expect(find.bySemanticsLabel('Play'), findsOneWidget);
    expect(find.text('-14:00'), findsOneWidget, reason: 'the whole recording is left before playing');
    expect(tester.getCenter(player).dx, lessThan(tester.getCenter(ask).dx));
    expect(tester.getSize(ask).height, 56);
    await tester.tap(ask);
    expect(asked, 1);

    await _pumpBar(tester, provider, onAskOmi: () => asked++);
    expect(player, findsNothing, reason: 'Summary shows the Ask Omi bar alone');
    expect(find.byKey(const ValueKey('detail_ask_omi')), findsOneWidget);
  });

  test('the waveform rises where people spoke and drops through silence', () {
    // 0-10 s talking, 10-30 s silent, 30-40 s talking.
    final levels = speechLevels([_segment(0, 10), _segment(30, 40)], 4);
    expect(levels, [1.0, 0.0, 0.0, 1.0]);
    expect(speechLevels([_segment(0, 5), _segment(15, 20)], 2), [0.5, 0.5]);
    expect(speechLevels(const [], 3), [0.0, 0.0, 0.0]);
    expect(speechLevels([_segment(2, 2)], 2), [1.0, 1.0], reason: 'a zero-length transcript is all speech');
  });

  testWidgets('transcript playback intent suppresses reviews even if audio is unavailable', (tester) async {
    final provider = _provider(_conversation(appResults: []));
    addTearDown(provider.dispose);
    Future<void> Function(double, double)? seek;
    var interactions = 0;
    await _pumpBar(
      tester,
      provider,
      onAudioInteraction: () => interactions++,
      onSeekFunctionReady: (callback) => seek = callback,
    );
    expect(interactions, 0);
    await seek!(0, 1);
    expect(interactions, 1);
    expect(tester.takeException(), isNull);
  });
}
