// Two reliability experiments for a conversation still in progress.
// no_live_player: its page has no audio player (the audio is still arriving).
// title_at_end: it reads "Listening" until it ends, whatever name the server holds for it.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

ServerConversation _conversation({required bool live, String title = 'Launch plan review'}) =>
    ServerConversation.fromJson({
      'id': 'open',
      'created_at': DateTime.utc(2026, 11, 26, 20).toIso8601String(),
      'started_at': DateTime.utc(2026, 11, 26, 20).toIso8601String(),
      'finished_at': DateTime.utc(2026, 11, 26, 20, 9).toIso8601String(),
      'source': 'omi',
      'status': live ? 'in_progress' : 'completed',
      'structured': {'title': title, 'overview': '', 'emoji': '🗓️'},
      'transcript_segments': [
        {'id': 's1', 'text': 'Stored words.', 'start': 0.0, 'end': 4.0, 'is_user': true},
      ],
      'audio_files': [
        {'id': 'a-1', 'uid': 'owner-1', 'conversation_id': 'open', 'chunk_timestamps': <double>[], 'duration': 540.0},
      ],
      'kind': 'conversation',
      'tile_state': live ? 'live' : 'done',
      'v3_recording_ids': ['uploaded-1'],
    });

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
    await SharedPreferencesUtil.init();
  });

  tearDown(() => ReliabilityExperiments.overrideForTesting(null));

  group('no_live_player', () {
    const player = ValueKey('detail_audio_player');
    const askBar = ValueKey('detail_ask_omi');

    Future<Future<void> Function(double, double)?> pumpBar(WidgetTester tester, ServerConversation conversation,
        {ConversationTab tab = ConversationTab.transcript}) async {
      final detail = ConversationDetailProvider()
        ..selectedDate = conversationLocalDayKey(conversation.createdAt)
        ..setCachedConversation(conversation);
      addTearDown(detail.dispose);
      final accounts = ConversationsV3Provider(
          uid: () => 'owner-1',
          cached: 'owner-1:1',
          fetchLive: () async => const ApiSuccess(ConversationsLiveRead(v3: true, conversation: null)));
      addTearDown(accounts.dispose);
      await accounts.refresh();
      Future<void> Function(double, double)? seek;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: MultiProvider(
            providers: [
              ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
              ChangeNotifierProvider<ConversationsV3Provider>.value(value: accounts),
            ],
            child: Scaffold(
              body: ConversationBottomBar(
                mode: ConversationBottomBarMode.detail,
                onSeekFunctionReady: (value) => seek = value,
                selectedTab: tab,
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
      return seek;
    }

    testWidgets('off: a conversation in progress shows the player over the audio saved so far', (tester) async {
      await pumpBar(tester, _conversation(live: true));

      expect(find.byKey(player), findsOneWidget);
      expect(find.byKey(askBar), findsNothing);
    });

    testWidgets('on: a conversation in progress has no player, and the bar is Ask Omi', (tester) async {
      ReliabilityExperiments.overrideForTesting({'no_live_player'});
      final seek = await pumpBar(tester, _conversation(live: true));

      expect(find.byKey(player), findsNothing);
      expect(find.bySemanticsLabel('Play'), findsNothing);
      expect(find.byKey(askBar), findsOneWidget);

      // A seek from the page (a source opened from Summary) loads and plays nothing.
      await seek?.call(0, 4);
      await tester.pump();
      expect(find.byKey(player), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('on: the player is back once the conversation has ended', (tester) async {
      ReliabilityExperiments.overrideForTesting({'no_live_player'});
      await pumpBar(tester, _conversation(live: true));
      expect(find.byKey(player), findsNothing);

      await pumpBar(tester, _conversation(live: false));
      expect(find.byKey(player), findsOneWidget);
      expect(find.bySemanticsLabel('Play'), findsOneWidget);
    });

    testWidgets('on: Summary of a conversation in progress is unchanged', (tester) async {
      ReliabilityExperiments.overrideForTesting({'no_live_player'});
      await pumpBar(tester, _conversation(live: true), tab: ConversationTab.summary);

      expect(find.byKey(player), findsNothing);
      expect(find.byKey(askBar), findsOneWidget);
    });
  });

  group('title_at_end', () {
    test('off: a conversation in progress shows the name the server gave it', () {
      expect(awaitsLiveTitle(_conversation(live: true)), isFalse);
      expect(awaitsLiveTitle(_conversation(live: true, title: '')), isTrue);
    });

    test('on: a conversation in progress has no name, an ended one keeps its own', () {
      ReliabilityExperiments.overrideForTesting({'title_at_end'});

      expect(awaitsLiveTitle(_conversation(live: true)), isTrue);
      expect(awaitsLiveTitle(_conversation(live: true, title: '')), isTrue);
      expect(awaitsLiveTitle(_conversation(live: false)), isFalse);
    });

    Future<String> rowTitle(WidgetTester tester, ServerConversation conversation) async {
      late String title;
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(builder: (context) {
          title = conversationRowTitle(context, conversation);
          return const SizedBox.shrink();
        }),
      ));
      return title;
    }

    testWidgets('Home row: Listening while in progress, the name once ended', (tester) async {
      expect(await rowTitle(tester, _conversation(live: true)), 'Launch plan review');

      ReliabilityExperiments.overrideForTesting({'title_at_end'});
      expect(await rowTitle(tester, _conversation(live: true)), 'Listening');
      expect(await rowTitle(tester, _conversation(live: false)), 'Launch plan review');
    });
  });
}
