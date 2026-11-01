import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  for (final outcome in ['undo', 'commit', 'cancel', 'partial failure', 'member']) {
    testWidgets('episode Delete includes unloaded discarded members in one Undo window: $outcome', (tester) async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      OmiColors.active = OmiColors.forBrightness(Brightness.light);
      final at = DateTime(2026, 10, 29, 18, 56);
      final visible = [
        for (final id in ['dinner', 'weekend'])
          ServerConversation(id: id, createdAt: at, startedAt: at, structured: Structured('Title $id', '')),
      ];
      final episode = Episode(
          id: 'e',
          live: false,
          startedAt: at,
          lastActivityAt: at,
          title: 'Dinner plans',
          conversationIds: ['dinner', 'weekend', 'discarded'],
          members: visible);
      final calls = <String>[];
      final history = ConversationProvider(isSignedIn: () => true)..conversations = [...visible];
      history.conversationDeleteFetcherOverride = (id) async {
        calls.add(id);
        return outcome != 'partial failure' || id != 'weekend';
      };
      final episodes = EpisodeProvider()
        ..debugSetLive(null)
        ..debugSetHomeEpisodes([episode]);
      episodes.observeHomeConversations(history);
      final connectivity = ConnectivityProvider();
      addTearDown(history.dispose);
      addTearDown(episodes.dispose);
      addTearDown(connectivity.dispose);
      await tester.pumpWidget(MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: history),
            ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
            ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
          ],
          child: MaterialApp(
            theme: buildOmiTheme(brightness: Brightness.light),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Builder(
                builder: (context) => Scaffold(
                        body: TextButton(
                      onPressed: () =>
                          Navigator.of(context).push(omiPageRoute(builder: (_) => EpisodePage(episode: episode))),
                      child: const Text('Open episode'),
                    ))),
          )));
      await tester.tap(find.text('Open episode'));
      await tester.pumpAndSettle();
      expect(find.text('Title dinner'), findsOneWidget);
      expect(find.text('Title weekend'), findsOneWidget);
      if (outcome == 'member') {
        await tester.longPress(find.text('Title dinner'));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const ValueKey('conversation_action_delete')));
        await tester.pumpAndSettle();
        expect(find.text('Delete Conversation?'), findsOneWidget);
        await tester.tap(find.text('Delete').last);
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('episode_page')), findsOneWidget);
        expect(history.memoriesToDelete.keys, ['dinner']);
        expect(find.text('Title dinner'), findsNothing);
        expect(find.text('Title weekend'), findsOneWidget);
        await tester.tap(find.text('Undo'));
        await tester.pumpAndSettle();
        expect(history.memoriesToDelete, isEmpty);
        expect(find.text('Title dinner'), findsOneWidget);
        expect(calls, isEmpty);
        await tester.pumpWidget(const SizedBox.shrink());
        return;
      }
      await tester.tap(find.byKey(const Key('episode_more')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();
      expect(find.text('Delete 3 Conversations?'), findsOneWidget);
      expect(history.memoriesToDelete, isEmpty);
      expect(calls, isEmpty);
      await tester.tap(find.text(outcome == 'cancel' ? 'Cancel' : 'Delete').last);
      await tester.pumpAndSettle();
      if (outcome == 'cancel') {
        expect(find.byKey(const Key('episode_page')), findsOneWidget);
        expect(history.conversations, visible);
      } else {
        expect(find.byKey(const Key('episode_page')), findsNothing);
        expect(history.memoriesToDelete.keys, unorderedEquals(episode.conversationIds));
        expect(episodes.hiddenHomeMembers, containsAll(episode.conversationIds));
        expect(history.conversations, isEmpty);
        expect(calls, isEmpty, reason: 'no DELETE until the shared Undo closes');
        expect(find.text('Undo'), findsOneWidget);
        if (outcome == 'undo') {
          await tester.tap(find.text('Undo'));
          await tester.pumpAndSettle();
          expect(history.memoriesToDelete, isEmpty);
          expect(episodes.hiddenHomeMembers, isEmpty);
          expect(history.conversations.where((c) => !c.discarded).map((c) => c.id),
              unorderedEquals(['dinner', 'weekend']));
          expect(history.conversations.singleWhere((c) => c.id == 'discarded').discarded, isTrue);
          await tester.pump(const Duration(seconds: 11));
          expect(calls, isEmpty);
        } else {
          await tester.pump(const Duration(seconds: 6));
          await tester.pumpAndSettle();
          expect(calls, unorderedEquals(episode.conversationIds));
          expect(history.memoriesToDelete, isEmpty);
          if (outcome == 'partial failure') {
            expect(history.conversations.single.id, 'weekend');
            expect(episodes.hiddenHomeMembers, {'dinner', 'discarded'});
          } else {
            expect(history.conversations, isEmpty);
            expect(episodes.hiddenHomeMembers, containsAll(episode.conversationIds));
          }
        }
      }
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
