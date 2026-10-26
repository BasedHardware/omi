import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/conversation_merge_journal.dart';

import 'support/hermetic_boot.dart';
import 'support/journey_evidence.dart';

// Real HTTP/client decoder, production provider, journal/cache and row widget.
// The loopback fixture substitutes authenticated backend IO and worker effects;
// backend TestClient/coordinator regressions exercise those owners separately.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  ServerConversation row(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 10, 26),
      structured: Structured(id, 'synthetic summary'),
      status: ConversationStatus.completed);

  testWidgets('two concurrent completion deliveries survive offline reopen as two target rows', (tester) async {
    final evidence = JourneyEvidence.begin(journeyId: 'j7_conversation_merge_recovery', lane: journeyLane);
    late ConversationProvider reopened;
    await tester.runAsync(() async {
      final server = await JourneyHermeticBoot.start();
      var stopped = false;
      addTearDown(() async {
        if (!stopped) await server.stop();
      });
      addTearDown(JourneyHermeticBoot.stop);
      server.conversations.addAll([
        for (final id in ['a', 'b', 'c', 'd']) row(id).toJson()
      ]);
      final provider = ConversationProvider(isSignedIn: () => true);
      await provider.fetchConversations();
      provider.watchMerge(['a', 'b'], targetId: 'target-ab');
      provider.watchMerge(['c', 'd'], targetId: 'target-cd');
      server.conversations
        ..clear()
        ..addAll([row('target-ab').toJson(), row('target-cd').toJson()]);
      await Future.wait([
        provider.onMergeCompleted('target-ab', ['a', 'b']),
        provider.onMergeCompleted('target-cd', ['c', 'd']),
      ]);
      expect(provider.conversations.map((c) => c.id), unorderedEquals(['target-ab', 'target-cd']));
      expect(server.countOf('GET', '/v1/conversations/target-ab'), 1);
      expect(server.countOf('GET', '/v1/conversations/target-cd'), 1);
      expect(ConversationMergeJournal(SharedPreferencesUtil().uid, Env.apiBaseUrl!).load(), isEmpty);
      provider.dispose();
      await server.stop();
      stopped = true;
      reopened = ConversationProvider(isSignedIn: () => true);
      addTearDown(reopened.dispose);
      expect(await reopened.fetchConversations(), false);
      expect(reopened.conversations.map((c) => c.id), unorderedEquals(['target-ab', 'target-cd']));
      expect(reopened.mergingConversationIds, isEmpty);
      evidence.record('concurrent-offline-cache',
          ok: true, invariant: 'both HTTP-resolved targets persist and no retired sources return offline');
    });
    await JourneyHermeticBoot.pumpPage(tester,
        page: Scaffold(
            body: Consumer<ConversationProvider>(
                builder: (_, p, __) => ListView(children: [
                      for (final c in p.conversations)
                        ConversationListItem(
                            conversation: c, conversationIdx: 0, date: conversationLocalDayKey(c.createdAt))
                    ]))),
        providers: [ChangeNotifierProvider<ConversationProvider>.value(value: reopened)]);
    await tester.pump();
    expect(find.text('target-ab'), findsOneWidget);
    expect(find.text('target-cd'), findsOneWidget);
    expect(find.text('a'), findsNothing);
    expect(find.byType(MergingIndicator), findsNothing);
    evidence.record('concurrent-offline-rows',
        ok: true, invariant: 'offline UI renders both targets without merge overlays');
    await evidence.write();
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final scenario in [(reopen: false, slow: false), (reopen: true, slow: false), (reopen: false, slow: true)]) {
    final reopen = scenario.reopen;
    final slow = scenario.slow;
    testWidgets(
        'no push: merge settles ${reopen ? 'after reopening' : slow ? 'after the fast polling window' : 'in foreground'} and renders only its new target',
        (tester) async {
      final evidence = JourneyEvidence.begin(journeyId: 'j7_conversation_merge_recovery', lane: journeyLane);
      evidence.note(reopen ? 'reopen while worker pending' : 'foreground without push');
      late ConversationProvider provider;
      await tester.runAsync(() async {
        final server = await JourneyHermeticBoot.start();
        addTearDown(server.stop);
        addTearDown(JourneyHermeticBoot.stop);
        server.conversations.addAll([row('source-a').toJson(), row('source-b').toJson()]);
        ConversationProvider make() => ConversationProvider(isSignedIn: () => true)
          ..mergeProbeInterval = const Duration(milliseconds: 10)
          ..mergeProbeLimit = slow ? const Duration(milliseconds: 150) : const Duration(minutes: 3)
          ..mergeRecoveryInterval = const Duration(milliseconds: 10);
        provider = make();
        await provider.fetchConversations();
        final admitted = await provider.initiateConversationMerge(conversationIds: ['source-a', 'source-b']);
        expect(admitted?.mergedConversationId, server.mergeTargetId);
        expect(server.countOf('POST', '/v1/conversations/merge'), 1);
        if (reopen) {
          provider.dispose();
          provider = make();
          await provider.fetchConversations();
        }
        addTearDown(provider.dispose);
        // Source deletion may be incomplete while the target is already ready.
        server.conversations.add(row(server.mergeTargetId).toJson());
        server.failNext('GET', '/v1/conversations/source-a', status: 402);
        final readObserved = Completer<void>();
        final wait = Timer.periodic(const Duration(milliseconds: 2), (timer) {
          if (server.countOf('GET', '/v1/conversations/source-a') > 0) {
            timer.cancel();
            readObserved.complete();
          }
        });
        await readObserved.future.timeout(const Duration(seconds: 5));
        wait.cancel();
        expect([...provider.conversations, ...provider.processingConversations].map((c) => c.id),
            containsAll(['source-a', 'source-b']));
        if (slow) {
          final recovery = Completer<void>();
          final untilRecovery = Timer.periodic(const Duration(milliseconds: 2), (timer) {
            if (server.countOf('GET', '/v1/conversations') >= 2) {
              timer.cancel();
              recovery.complete();
            }
          });
          await recovery.future.timeout(const Duration(seconds: 5));
          untilRecovery.cancel();
          expect(provider.mergingConversationIds, containsAll(['source-a', 'source-b']));
        }
        final settled = Completer<void>();
        provider.addListener(() {
          if (!settled.isCompleted &&
              provider.conversations.length == 1 &&
              provider.conversations.single.id == server.mergeTargetId) {
            settled.complete();
          }
        });
        server.conversations.removeWhere((c) => c['id'] != server.mergeTargetId);
        await settled.future.timeout(const Duration(seconds: 5));
        expect(provider.mergingConversationIds, isEmpty);
        expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), [server.mergeTargetId]);
        expect(server.countOf('POST', '/v1/conversations/merge'), 1, reason: 'resume cannot resubmit a merge');
        evidence.record('http-cache-recovery',
            ok: true,
            invariant:
                'sources vanish only after authoritative deletion; same admitted target survives restart without push');
      });
      await JourneyHermeticBoot.pumpPage(tester,
          page: Scaffold(
              body: Consumer<ConversationProvider>(
                  builder: (_, p, __) => ListView(children: [
                        for (final c in p.conversations)
                          ConversationListItem(
                              conversation: c, conversationIdx: 0, date: conversationLocalDayKey(c.createdAt))
                      ]))),
          providers: [ChangeNotifierProvider<ConversationProvider>.value(value: provider)]);
      await tester.pump();
      expect(find.text('fixture-new-merge-target'), findsOneWidget);
      expect(find.text('source-a'), findsNothing);
      expect(find.byType(MergingIndicator), findsNothing);
      evidence.record('rendered-settled-row', ok: true, invariant: 'one target row and no merging overlay');
      await evidence.write();
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
