import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';

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

  for (final reopen in [false, true]) {
    testWidgets(
        'no push: merge settles ${reopen ? 'after reopening' : 'in foreground'} and renders only its new target',
        (tester) async {
      final evidence = JourneyEvidence.begin(journeyId: 'j7_conversation_merge_recovery', lane: journeyLane);
      evidence.note(reopen ? 'reopen while worker pending' : 'foreground without push');
      late ConversationProvider provider;
      await tester.runAsync(() async {
        final server = await JourneyHermeticBoot.start();
        addTearDown(server.stop);
        addTearDown(JourneyHermeticBoot.stop);
        server.conversations.addAll([row('source-a').toJson(), row('source-b').toJson()]);
        ConversationProvider make() =>
            ConversationProvider(isSignedIn: () => true)..mergeProbeInterval = const Duration(milliseconds: 10);
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
        final settled = Completer<void>();
        provider.addListener(() {
          if (!settled.isCompleted &&
              provider.conversations.length == 1 &&
              provider.conversations.single.id == server.mergeTargetId) settled.complete();
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
