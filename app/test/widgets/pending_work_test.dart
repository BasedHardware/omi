import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/activity/activity_bell_button.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/activity/needs_attention_section.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';

/// Failures stay behind the bell; catch-up work alone never lights its dot.

class _IdleSync extends ChangeNotifier implements SyncProvider {
  @override
  List<Wal> get allWals => const [];
  @override
  List<Wal> get displaySortedWals => const [];
  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isRateLimited => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

AttentionItem _item(String id, {String? title, bool seen = false}) => AttentionItem(
      id: id,
      kind: 'conversation_summary_failed',
      conversationId: 'c-$id',
      title: title,
      retryable: true,
      seen: seen,
      retryState: AttentionRetryState.none,
    );

Future<PendingWorkStore> _store({
  List<PendingWorkItem> pending = const [],
  List<AttentionItem> attention = const [],
  List<String>? retried,
  List<String>? retriedAll,
}) async {
  final store = PendingWorkStore(
    loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, items: pending, attentionUnseenCount: 0)),
    loadAttention: () async => ApiSuccess(AttentionItemsPage(enabled: true, items: attention, unseenCount: 0)),
    retry: (id, {required idempotencyKey}) async {
      retried?.add(id);
      return ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress));
    },
    retryAll: ({required idempotencyKey}) async {
      retriedAll?.add(idempotencyKey);
      return const ApiSuccess([]);
    },
    markSeen: (_) async => const ApiSuccess(null),
  );
  await store.refresh();
  return store;
}

ConversationProvider _conversations({List<ServerConversation> processing = const []}) => ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    )..processingConversations = processing;

Widget _app(Widget child, {ConversationProvider? conversations, SyncProvider? sync}) => MultiProvider(
      providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: sync ?? _IdleSync()),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations ?? _conversations()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    );

void main() {
  group('Needs attention', () {
    testWidgets('lists failed conversations with Try Again and Retry all', (tester) async {
      final retried = <String>[];
      final retriedAll = <String>[];
      final store = await _store(
        attention: [_item('x', title: 'Launch planning'), _item('y')],
        retried: retried,
        retriedAll: retriedAll,
      );
      await tester.pumpWidget(_app(NeedsAttentionSection(store: store, syncProvider: _IdleSync())));
      expect(find.text('NEEDS ATTENTION'), findsOneWidget);
      expect(find.text('Launch planning'), findsOneWidget);
      expect(find.text("Couldn't summarize this conversation"), findsNWidgets(2));
      expect(find.text('Try Again'), findsNWidgets(2));

      await tester.tap(find.text('Try Again').first);
      await tester.pump();
      expect(retried, ['x']);
      // One item is in flight: Retry all needs two idle items, so it is gone.
      expect(find.byKey(const Key('activity_retry_all')), findsNothing);
    });

    testWidgets('Retry all shows for two or more idle items and sends one key', (tester) async {
      final retriedAll = <String>[];
      final store = await _store(attention: [_item('x'), _item('y')], retriedAll: retriedAll);
      await tester.pumpWidget(_app(NeedsAttentionSection(store: store, syncProvider: _IdleSync())));
      await tester.tap(find.byKey(const Key('activity_retry_all')));
      await tester.pump();
      expect(retriedAll, hasLength(1));
    });
  });

  group('bell', () {
    testWidgets('catch-up alone never lights either bell dot', (tester) async {
      final store = await _store(pending: const [
        PendingWorkItem(id: 'sync:j', kind: 'sync_job', state: 'transcribing', conversationIds: ['a', 'b']),
      ]);
      var stored = DateTime.now().millisecondsSinceEpoch;
      final seen = ActivitySeen(read: () => stored, write: (v) => stored = v, owner: () => 'u');
      await tester.pumpWidget(_app(ActivityBellButton(seen: seen, pendingWork: store)));
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
      expect(find.byKey(const ValueKey('home_activity_dot')), findsNothing);
    });

    testWidgets('unseen attention lights the warning dot; no recap needed', (tester) async {
      final store = await _store(attention: [_item('x')]);
      var stored = DateTime.now().millisecondsSinceEpoch;
      final seen = ActivitySeen(read: () => stored, write: (v) => stored = v, owner: () => 'u');
      await tester.pumpWidget(_app(ActivityBellButton(seen: seen, pendingWork: store)));
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsOneWidget);
      await store.markSeen();
      await tester.pump();
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
    });

    testWidgets('seen attention items do not light it', (tester) async {
      final store = await _store(attention: [_item('x', seen: true)]);
      var stored = DateTime.now().millisecondsSinceEpoch;
      final seen = ActivitySeen(read: () => stored, write: (v) => stored = v, owner: () => 'u');
      await tester.pumpWidget(_app(ActivityBellButton(seen: seen, pendingWork: store)));
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
      expect(find.byKey(const ValueKey('home_activity_dot')), findsNothing);
    });
  });
}
