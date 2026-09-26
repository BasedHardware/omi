// IMG_1160: a 5m 49s conversation whose saved audio is 3 s. The player says how much audio was
// saved instead of looking like a broken recording; a whole recording says nothing extra.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  ServerConversation conversation({required double audioSeconds}) {
    final start = DateTime(2026, 9, 26, 11, 38).toUtc();
    return ServerConversation(
      id: 'conv-audio',
      createdAt: start,
      startedAt: start,
      finishedAt: start.add(const Duration(minutes: 5, seconds: 49)),
      structured: Structured('Music and Casual Conversation', ''),
      audioFiles: [
        AudioFile(
          id: 'a1',
          uid: 'u',
          conversationId: 'conv-audio',
          chunkTimestamps: const [],
          startedAt: start,
          duration: audioSeconds,
        ),
      ],
    );
  }

  Future<void> pump(WidgetTester tester, ServerConversation item) async {
    final provider = ConversationDetailProvider()..setCachedConversation(item);
    addTearDown(provider.dispose);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: ChangeNotifierProvider<ConversationDetailProvider>.value(
        value: provider,
        child: Scaffold(
          body: ConversationBottomBar(
            mode: ConversationBottomBarMode.detail,
            selectedTab: ConversationTab.summary,
            onTabSelected: (_) {},
            onStopPressed: () {},
            conversation: item,
          ),
        ),
      ),
    ));
    await tester.pump();
  }

  testWidgets('3 s of audio for a 5m 49s conversation says how much was saved', (tester) async {
    await pump(tester, conversation(audioSeconds: 3));
    expect(find.byKey(const Key('conversation_audio_card')), findsOneWidget);
    expect(find.text(en.audioPartiallySaved('0:03', '5:49')), findsOneWidget);
  });

  testWidgets('a whole recording shows just the player', (tester) async {
    await pump(tester, conversation(audioSeconds: 349));
    expect(find.byKey(const Key('conversation_audio_card')), findsOneWidget);
    expect(find.byKey(const Key('conversation_audio_partial')), findsNothing);
  });
}
