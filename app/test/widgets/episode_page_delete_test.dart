import 'dart:async';
import 'package:omi/backend/http/api_result.dart';
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
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  for (final synthetic in [false, true]) {
    for (final outcome in ['undo', 'commit', 'becomes ready']) {
      final undo = outcome == 'undo';
      testWidgets('processing Delete and Undo touch displayed pending only: synthetic=$synthetic outcome=$outcome',
          (tester) async {
        SharedPreferences.setMockInitialValues({});
        await SharedPreferencesUtil.init();
        OmiColors.active = OmiColors.forBrightness(Brightness.light);
        final at = DateTime(2026, 11, 15, 9);
        ServerConversation member(String id, String step, {bool discarded = false, bool deleted = false}) =>
            ServerConversation(
                id: id,
                createdAt: at,
                startedAt: at,
                homeStep: step,
                discarded: discarded,
                deleted: deleted,
                structured: Structured('Fixture $id', ''));
        final pending = member('pending', 'transcribing');
        final others = [
          member('failed', 'failed'),
          member('discarded', 'writing_notes', discarded: true),
          member('deleted', 'writing_notes', deleted: true),
          member('ready', 'ready')
        ];
        final owner = Episode(
            id: 'owner',
            live: synthetic && outcome == 'becomes ready',
            startedAt: at,
            lastActivityAt: at,
            closedAt: at,
            conversationIds: [pending.id, ...others.map((c) => c.id)],
            members: [pending, ...others]);
        final projection = synthetic
            ? Episode(
                id: '',
                live: false,
                startedAt: at,
                lastActivityAt: at,
                conversationIds: owner.conversationIds,
                members: [pending])
            : owner.copyWith(members: [pending]);
        final calls = <String>[];
        final history = ConversationProvider(isSignedIn: () => true)..conversations = [pending, ...others];
        history.conversationDeleteFetcherOverride = (id) async {
          calls.add(id);
          return true;
        };
        var lookups = 0;
        final episodes = EpisodeProvider(
            detail: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
            lookup: (_) async {
              lookups++;
              return ApiSuccess(EpisodeRead(enabled: true, episode: owner));
            })
          ..debugSetLive(null)
          ..debugSetHomeEpisodes(synthetic ? [] : [owner]);
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
              home: Scaffold(
                  body: ProcessingConversationRow(
                      conversation: pending, episode: projection, processingEpisodes: synthetic ? [] : [owner])),
            )));
        await tester.tap(find.byKey(const Key('home_processing_row')));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byKey(const ValueKey('processing_episode_owner')), findsOneWidget);
        expect(lookups, synthetic ? 1 : 0, reason: 'cold cards resolve their owner only on page open');
        if (outcome == 'becomes ready') {
          history.updateConversation(pending.withHomeStep('ready'), preserveHomeStep: false);
          await tester.pump();
          expect(find.byKey(const ValueKey('episode_member_pending')), findsNothing);
          expect(find.byKey(const ValueKey('processing_episode_owner')), findsOneWidget,
              reason: 'the source remains reachable after the last pending member becomes READY');
        } else {
          expect(find.byKey(const ValueKey('episode_member_pending')), findsOneWidget);
        }
        for (final other in others) {
          expect(find.byKey(ValueKey('episode_member_${other.id}')), findsNothing);
        }
        await tester.tap(find.byKey(const Key('episode_more')));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.tap(find.text('Delete'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        if (outcome == 'becomes ready') {
          expect(find.text('Delete 1 Conversation?'), findsNothing);
          expect(history.memoriesToDelete, isEmpty);
          expect(episodes.hiddenHomeMembers, isEmpty);
          expect(calls, isEmpty);
          expect(history.conversations.map((c) => c.id), unorderedEquals(owner.conversationIds));
          await tester.pumpWidget(const SizedBox.shrink());
          return;
        }
        expect(find.text('Delete 1 Conversation?'), findsOneWidget);
        await tester.tap(find.text('Delete').last);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(history.memoriesToDelete.keys, ['pending']);
        expect(episodes.hiddenHomeMembers, {'pending'});
        expect(history.conversations.map((c) => c.id), unorderedEquals(others.map((c) => c.id)));
        expect(calls, isEmpty);
        if (undo) {
          await tester.tap(find.text('Undo'));
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 500));
          expect(history.memoriesToDelete, isEmpty);
          expect(episodes.hiddenHomeMembers, isEmpty);
          expect(history.conversations.map((c) => c.id), unorderedEquals(owner.conversationIds));
          expect(history.conversations.singleWhere((c) => c.id == 'discarded').discarded, isTrue);
          expect(history.conversations.singleWhere((c) => c.id == 'deleted').deleted, isTrue);
        }
        await tester.pump(const Duration(seconds: 11));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(calls, undo ? isEmpty : ['pending']);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }
  for (final outcome in ['undo', 'commit', 'cancel', 'partial failure', 'member', 'seed loading']) {
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
      final hydrated = Completer<ApiResult<Episode>>();
      final episodes = EpisodeProvider(
          detail: (_) async => outcome == 'seed loading'
              ? await hydrated.future
              : const ApiFailure<Episode>(ApiProblem(ApiProblemKind.transport)))
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
                      onPressed: () => Navigator.of(context).push(omiPageRoute(
                          builder: (_) => EpisodePage(
                              episode: outcome == 'seed loading'
                                  ? episode.copyWith(members: [], conversationIds: [])
                                  : episode,
                              displaySeedOnly: outcome == 'seed loading'))),
                      child: const Text('Open episode'),
                    ))),
          )));
      await tester.tap(find.text('Open episode'));
      if (outcome == 'seed loading') {
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 400));
        await tester.tap(find.byKey(const Key('episode_more')));
        await tester.pump(const Duration(milliseconds: 400));
        await tester.tap(find.text('Delete'));
        await tester.pump(const Duration(milliseconds: 400));
        expect(find.text('Delete 3 Conversations?'), findsNothing);
        expect(history.memoriesToDelete, isEmpty);
        expect(calls, isEmpty);
        hydrated.complete(ApiSuccess(episode));
      }
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
