import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/capture/optimistic_processing.dart';

import '../support/typed_conversation_screen.dart';

void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);
  for (final live in [false, true]) {
    testWidgets('Home closing episode (live snapshot=$live) has one processing row until all members finish',
        (tester) async {
      tester.view.physicalSize = const Size(390, 1400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      // Keep this lifecycle fixture outside the unrelated, wall-clock New badge window.
      final now = DateTime.now().subtract(const Duration(hours: 1));
      ServerConversation member(String id, ConversationStatus status) => ServerConversation(
            id: id,
            createdAt: now,
            startedAt: now,
            status: status,
            structured: Structured(status == ConversationStatus.completed ? 'Finished $id' : '', ''),
          );
      final a = member('a', ConversationStatus.completed);
      final b = member('b', ConversationStatus.processing);
      final c = member('c', ConversationStatus.processing);
      Episode episode(bool live) => Episode(
            id: 'closing',
            live: live,
            startedAt: now,
            lastActivityAt: now,
            conversationIds: const ['a', 'b', 'c'],
            members: [a, b, c],
            title: 'Dinner and plans',
          );
      final provider = ConversationProvider(isSignedIn: () => false)
        ..isLoadingConversations = false
        ..conversations = [a]
        ..processingConversations = [b, c]
        ..groupConversationsByDate();
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [episode(live)])),
      );
      addTearDown(provider.dispose);
      addTearDown(episodes.dispose);
      final screen = await buildTypedConversationScreen(provider, episodes: episodes);
      episodes
        ..debugSetLive(null)
        ..debugSetHomeEpisodes([episode(live)]);
      await tester.pumpWidget(screen);
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
      expect(find.byType(ConversationListItem), findsNothing);
      provider.removeProcessingConversation('b');
      await tester.pump();
      expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
      provider.removeProcessingConversation('c');
      provider
        ..processingConversations = []
        ..conversations = [a, member('b', ConversationStatus.completed), member('c', ConversationStatus.completed)]
        ..groupConversationsByDate();
      episodes.debugSetHomeEpisodes([episode(false)]);
      await tester.pump();
      expect(find.byKey(const Key('home_processing_row')), findsNothing);
      expect(find.byType(ConversationListItem), findsOneWidget);
      expect(find.text('Dinner and plans'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets('Home local Processing row expires without a server response', (tester) async {
    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final provider = ConversationProvider(isSignedIn: () => false)..isLoadingConversations = false;
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider);
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pumpWidget(screen);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
    await tester.pump(OptimisticProcessingPlaceholder.timeout);
    await tester.pump();
    expect(find.byKey(const Key('home_processing_row')), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('Home optimistic row becomes the completed server row without title or emoji', (tester) async {
    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final completed = ServerConversation(
      id: 'finished',
      createdAt: DateTime.now(),
      structured: Structured('', ''),
      status: ConversationStatus.completed,
    );
    final provider = ConversationProvider(
      isSignedIn: () => true,
      conversationListFetcher: () async => (items: [completed], ok: true),
      conversationLifecycleFetcher: (_) async => (item: completed, ok: true),
    )..isLoadingConversations = false;
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider);
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation(targetConversationId: 'finished'));
    await tester.pumpWidget(screen);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
    await provider.forceRefreshConversations();
    await tester.pump();
    expect(find.byKey(const Key('home_processing_row')), findsNothing);
    expect(find.byType(ConversationListItem), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final targets in <List<String>>[
    [],
    ['a'],
    ['a', 'b']
  ]) {
    for (final loading in [false, true]) {
      testWidgets('Home has no pending row for server targets=$targets, loading=$loading', (tester) async {
        tester.view.physicalSize = const Size(390, 1400);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final store = PendingWorkStore(
          loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, attentionUnseenCount: 0, items: [
            PendingWorkItem(
                id: 'sync:job',
                kind: 'sync_job',
                state: 'transcribing',
                conversationIds: targets,
                durationSeconds: 720),
          ])),
          loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
        );
        final provider = ConversationProvider(isSignedIn: () => false)..isLoadingConversations = loading;
        addTearDown(store.dispose);
        addTearDown(provider.dispose);
        final screen = await buildTypedConversationScreen(provider, pendingWork: store);
        await store.refresh();
        provider.processingConversations = [
          ServerConversation(
              id: 'processing',
              createdAt: DateTime.now(),
              structured: Structured('', ''),
              status: ConversationStatus.processing),
        ];
        await tester.pumpWidget(screen);
        await tester.pump(const Duration(milliseconds: 300));
        expect(find.byKey(const Key('home_pending_row')), findsNothing);
        expect(find.text('Conversations on the way'), findsNothing);
        expect(find.text('Catching up on earlier audio'), findsNothing);
        provider.removeProcessingConversation('processing');
        await provider.addConversation(ServerConversation(
            id: 'done',
            createdAt: DateTime.now(),
            structured: Structured('Finished recording', 'Overview'),
            status: ConversationStatus.completed));
        provider.setLoadingConversations(false);
        await tester.pump();
        expect(find.byKey(const Key('home_pending_row')), findsNothing);
        expect(find.byType(ConversationListItem), findsOneWidget);
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }
}
