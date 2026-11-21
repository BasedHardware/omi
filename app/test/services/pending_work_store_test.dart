import 'dart:async';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/gen/pending_work_wire.g.dart' as wire;
import 'package:omi/services/pending_work/pending_work_store.dart';

/// The one-row Home and the bell's Needs attention read one store; retries reuse one idempotency
/// key until the server answers.

AttentionItem _item(String id, {bool seen = false, bool retryable = true, String? conversationId}) => AttentionItem(
      id: id,
      kind: 'conversation_summary_failed',
      conversationId: conversationId ?? 'c-$id',
      retryable: retryable,
      seen: seen,
      retryState: AttentionRetryState.none,
    );

class _Calls {
  int pending = 0;
  int attention = 0;
  final retryKeys = <String>[];
  final retryAllKeys = <String>[];
  final seen = <List<String>>[];
}

PendingWorkStore _store(
  _Calls calls, {
  ApiResult<PendingWorkSnapshot>? pending,
  ApiResult<AttentionItemsPage>? attention,
  ApiResult<AttentionRetryResult> Function(String id)? retry,
  ApiResult<List<AttentionRetryResult>> Function()? retryAll,
  Future<ApiResult<void>> Function(String id)? dismiss,
  List<String>? dismissedStore,
  Map<String, List<String>>? dismissedByUid,
  String Function()? uid,
}) {
  var keys = 0;
  return PendingWorkStore(
    loadPending: () async {
      calls.pending++;
      return pending ?? const ApiSuccess(PendingWorkSnapshot.disabled);
    },
    loadAttention: () async {
      calls.attention++;
      return attention ?? const ApiSuccess(AttentionItemsPage.disabled);
    },
    retry: (id, {required idempotencyKey}) async {
      calls.retryKeys.add(idempotencyKey);
      return retry?.call(id) ??
          ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress, operationId: 'op'));
    },
    retryAll: ({required idempotencyKey}) async {
      calls.retryAllKeys.add(idempotencyKey);
      return retryAll?.call() ?? const ApiSuccess([]);
    },
    markSeen: (ids) async {
      calls.seen.add(ids);
      return const ApiSuccess(null);
    },
    dismiss: dismiss ?? (_) async => const ApiSuccess(null),
    loadDismissed: (owner) => [...?(dismissedByUid?[owner] ?? dismissedStore)],
    saveDismissed: (owner, ids) {
      if (dismissedByUid != null) {
        dismissedByUid[owner] = [...ids];
      } else {
        dismissedStore
          ?..clear()
          ..addAll(ids);
      }
    },
    currentUid: uid ?? () => 'u1',
    newKey: () => 'key-${keys++}',
  );
}

void main() {
  test('placement requires an explicit true wire confirmation', () {
    for (final value in [null, false, true]) {
      final json = <String, dynamic>{
        'enabled': true,
        'items': [],
        'attention_unseen_count': 0,
        if (value != null) 'home_processing_today': value
      };
      expect(PendingWorkSnapshot.fromJson(json).homeProcessingToday, value == true);
      expect(PendingWorkSnapshot.fromGenerated(wire.GeneratedPendingWorkSnapshot.fromJson(json)).homeProcessingToday,
          value == true);
    }
  });

  test('every failed read keeps the last good answer after a successful opt-in (X17)', () async {
    for (final kind in ApiProblemKind.values) {
      var failing = false;
      final store = PendingWorkStore(
          loadPending: () async => failing
              ? ApiFailure(ApiProblem(kind))
              : const ApiSuccess(
                  PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)),
          loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled));
      expect(store.homeProcessingToday, isFalse);
      await store.refresh();
      expect(store.homeProcessingToday, isTrue);
      failing = true;
      await store.refresh();
      expect(store.homeProcessingToday, kind != ApiProblemKind.notFound, reason: kind.name);
      store.dispose();
    }
  });

  test('thrown reads keep the last answer (X17); account reset restores old placement', () async {
    var throwing = false;
    final store = PendingWorkStore(
        loadPending: () async {
          if (throwing) throw StateError('offline');
          return const ApiSuccess(
              PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true));
        },
        loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled));
    await store.refresh();
    throwing = true;
    await store.refresh();
    expect(store.homeProcessingToday, isTrue);
    store.reset();
    await store.refresh();
    expect(store.homeProcessingToday, isFalse, reason: 'a new account with no answer keeps old Home');
    throwing = false;
    await store.refresh();
    store.reset();
    expect(store.homeProcessingToday, isFalse);
    expect(store.pending, isEmpty);
    store.dispose();
  });

  test('an old account response cannot enable placement after reset', () async {
    final response = Completer<ApiResult<PendingWorkSnapshot>>();
    final store = PendingWorkStore(
        loadPending: () => response.future, loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled));
    final refreshing = store.refresh();
    store.reset();
    response.complete(const ApiSuccess(
        PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)));
    await refreshing;
    expect(store.homeProcessingToday, isFalse);
    store.dispose();
  });

  test('failed pending rows belong only to Activity when on; off restores catch-up', () async {
    var enabled = true;
    final store = PendingWorkStore(
        loadPending: () async => ApiSuccess(PendingWorkSnapshot(
            enabled: true,
            homeProcessingToday: enabled,
            items: const [
              PendingWorkItem(
                  id: 'conv:f', kind: 'conversation', state: 'summarizing', conversationIds: ['f'], homeStep: 'failed')
            ],
            attentionUnseenCount: 0)),
        loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled));
    await store.refresh();
    expect(store.pending, isEmpty);
    expect(store.pendingForActivity.single.homeStep, 'failed');
    enabled = false;
    await store.refresh();
    expect(store.pending.single.id, 'conv:f');
    final wireItem = PendingWorkItem.fromJson(
        {'id': 'conv:f', 'kind': 'conversation', 'state': 'summarizing', 'home_step': 'failed'});
    expect(wireItem!.homeStep, 'failed');
    store.dispose();
  });

  test('confirmed failed ledger attempt uses a fresh key for the next retry', () async {
    final calls = _Calls();
    final store = _store(calls,
        attention: ApiSuccess(AttentionItemsPage(enabled: true, items: [_item('x')], unseenCount: 1)),
        retry: (id) => ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.failed)));
    await store.refresh();
    await store.retry(store.attention.single);
    await store.retry(store.attention.single);
    expect(calls.retryKeys, ['key-0', 'key-1']);
    store.dispose();
  });

  test('generated pending work keeps the recording count and legacy default', () {
    for (final count in [null, 3]) {
      final decoded = wire.GeneratedPendingWorkSnapshot.fromJson({
        'enabled': true,
        'attention_unseen_count': 0,
        'items': [
          {
            'id': 'sync:job',
            'kind': 'sync_job',
            'state': 'transcribing',
            'conversation_ids': ['target'],
            'duration_seconds': 0,
            'started_at': null,
            'updated_at': null,
            if (count != null) 'recording_count': count,
          }
        ],
      });
      final snapshot = PendingWorkSnapshot.fromGenerated(decoded);
      expect(snapshot.items.single.recordingCount, count ?? 1);
    }
  });

  test('a backend answering enabled:false reads as empty', () async {
    final calls = _Calls();
    final store = _store(calls);
    await store.refresh();
    expect(calls.pending + calls.attention, 2);
    expect(store.pending, isEmpty);
    expect(store.attention, isEmpty);
  });

  test('server items load and unseen attention lights the bell', () async {
    final calls = _Calls();
    final store = _store(
      calls,
      pending: const ApiSuccess(PendingWorkSnapshot(
        enabled: true,
        items: [
          PendingWorkItem(id: 'conv:a', kind: 'conversation', state: 'summarizing', conversationIds: ['a'])
        ],
        attentionUnseenCount: 1,
      )),
      attention: ApiSuccess(AttentionItemsPage(enabled: true, items: [_item('x')], unseenCount: 1)),
    );
    await store.refresh();
    expect(store.pending.single.id, 'conv:a');
    expect(store.attention.single.id, 'x');
    expect(store.hasUnseenAttention.value, isTrue);
  });

  test('an older backend (404) reads as empty; a transient failure keeps the last rows', () async {
    final calls = _Calls();
    var fail = false;
    final store = PendingWorkStore(
      loadPending: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
      loadAttention: () async => fail
          ? const ApiFailure(ApiProblem(ApiProblemKind.server))
          : ApiSuccess(AttentionItemsPage(enabled: true, items: [_item('x')], unseenCount: 1)),
      markSeen: (ids) async {
        calls.seen.add(ids);
        return const ApiSuccess(null);
      },
    );
    await store.refresh();
    expect(store.pending, isEmpty);
    expect(store.attention, hasLength(1));
    fail = true;
    await store.refresh();
    expect(store.attention, hasLength(1));
  });

  test('a failed retry keeps its key, so the next tap replays the same claim', () async {
    final calls = _Calls();
    var failNext = true;
    final store = _store(
      calls,
      attention: ApiSuccess(AttentionItemsPage(enabled: true, items: [_item('x')], unseenCount: 1)),
      retry: (id) {
        if (failNext) {
          failNext = false;
          return const ApiFailure(ApiProblem(ApiProblemKind.transport));
        }
        return ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress));
      },
    );
    await store.refresh();
    expect(await store.retry(store.attention.single), isFalse);
    expect(store.attention.single.retryState, AttentionRetryState.none);
    expect(await store.retry(store.attention.single), isTrue);
    expect(calls.retryKeys, ['key-0', 'key-0']);
    expect(store.attention.single.retryState, AttentionRetryState.inProgress);
    // In progress: a further tap sends nothing.
    expect(await store.retry(store.attention.single), isFalse);
    expect(calls.retryKeys, hasLength(2));
  });

  test('Retry all reuses its key until the server answers, then takes a fresh one', () async {
    final calls = _Calls();
    var fail = true;
    final store = _store(
      calls,
      attention: ApiSuccess(AttentionItemsPage(enabled: true, items: [_item('x'), _item('y')], unseenCount: 2)),
      retryAll: () => fail
          ? const ApiFailure(ApiProblem(ApiProblemKind.transport))
          : const ApiSuccess([
              AttentionRetryResult(itemId: 'x', state: AttentionRetryState.inProgress),
              AttentionRetryResult(itemId: 'y', state: AttentionRetryState.succeeded),
            ]),
    );
    await store.refresh();
    expect(await store.retryAll(), isFalse);
    expect(store.attention.every((i) => i.retryState == AttentionRetryState.none), isTrue);
    fail = false;
    expect(await store.retryAll(), isTrue);
    expect(calls.retryAllKeys, ['key-0', 'key-0']);
    expect(store.attention.map((i) => i.retryState), [AttentionRetryState.inProgress, AttentionRetryState.succeeded]);
  });

  test('markSeen sends only unseen ids once and darkens the bell', () async {
    final calls = _Calls();
    final store = _store(
      calls,
      attention: ApiSuccess(AttentionItemsPage(
        enabled: true,
        items: [_item('x'), _item('y', seen: true)],
        unseenCount: 1,
      )),
    );
    await store.refresh();
    await store.markSeen();
    await store.markSeen();
    expect(calls.seen, [
      ['x'],
    ]);
    expect(store.hasUnseenAttention.value, isFalse);
  });

  test('wire parsing tolerates malformed rows', () {
    final page = AttentionItemsPage.fromJson({
      'enabled': true,
      'items': [
        {
          'id': 'x',
          'kind': 'conversation_summary_failed',
          'retryable': true,
          'retry': {'state': 'in_progress'}
        },
        {'kind': 'missing id'},
        'not an object',
      ],
      'unseen_count': 1,
    });
    expect(page.items.single.retryState, AttentionRetryState.inProgress);
    final pending = PendingWorkSnapshot.fromJson({'enabled': false});
    expect(pending.enabled, isFalse);
    expect(pending.items, isEmpty);
  });

  group('dismiss', () {
    ApiResult<AttentionItemsPage> page(List<AttentionItem> items) =>
        ApiSuccess(AttentionItemsPage(enabled: true, items: items, unseenCount: 0));

    test('removes the row before the server answers and keeps it gone', () async {
      final answer = Completer<ApiResult<void>>();
      final dismissed = <String>[];
      final store = _store(_Calls(), attention: page([_item('x'), _item('y')]), dismiss: (id) {
        dismissed.add(id);
        return answer.future;
      });
      await store.refresh();
      final pending = store.dismiss(store.attention.first);
      expect(store.attention.map((i) => i.id), ['y']);
      expect(dismissed, ['x']);
      answer.complete(const ApiSuccess(null));
      expect(await pending, isTrue);
      expect(store.attention.map((i) => i.id), ['y']);
      // Activity's projected failure row for the same conversation stays hidden.
      expect(store.attentionConversationIds, containsAll(['c-x', 'c-y']));
    });

    test('a failed request puts the row back in place with the quiet error line', () async {
      final store = _store(_Calls(),
          attention: page([_item('x'), _item('y'), _item('z')]),
          dismiss: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
      await store.refresh();
      expect(await store.dismiss(store.attention[1]), isFalse);
      expect(store.attention.map((i) => i.id), ['x', 'y', 'z']);
      expect(store.retryErrors, {'y'});
      expect(store.attentionConversationIds, {'c-x', 'c-y', 'c-z'});
    });

    test('a dismissed conversation stays out of the failure projection after a relaunch', () async {
      final saved = <String>[];
      final first = _store(_Calls(), attention: page([_item('x')]), dismissedStore: saved);
      await first.refresh();
      await first.dismiss(first.attention.single);
      expect(saved, ['c-x']);
      first.reset();
      expect(first.attentionConversationIds, contains('c-x'));
      final relaunched = _store(_Calls(), dismissedStore: saved);
      await relaunched.refresh();
      expect(relaunched.attentionConversationIds, {'c-x'});
    });

    test('a failed dismiss forgets the saved conversation', () async {
      final saved = <String>[];
      final store = _store(_Calls(),
          attention: page([_item('x')]),
          dismissedStore: saved,
          dismiss: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
      await store.refresh();
      await store.dismiss(store.attention.single);
      expect(saved, isEmpty);
    });

    test('an account switch neither hides nor re-saves the old account\'s conversations', () async {
      var uid = 'a';
      final saved = <String, List<String>>{};
      var items = [_item('x')];
      final store = PendingWorkStore(
        loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
        loadAttention: () async => page(items),
        dismiss: (_) async => const ApiSuccess(null),
        loadDismissed: (owner) => [...?saved[owner]],
        saveDismissed: (owner, ids) => saved[owner] = [...ids],
        currentUid: () => uid,
      );
      await store.refresh();
      await store.dismiss(store.attention.single);
      expect(saved, {
        'a': ['c-x']
      });

      uid = 'b';
      store.reset();
      expect(store.attentionConversationIds, isEmpty);
      items = [_item('y')];
      await store.refresh();
      await store.dismiss(store.attention.single);
      expect(saved, {
        'a': ['c-x'],
        'b': ['c-y']
      });
      expect(store.attentionConversationIds, {'c-y'});

      uid = 'a';
      store.reset();
      expect(store.attentionConversationIds, {'c-x'});
    });

    test('a new failure for a dismissed conversation shows again and leaves the saved list', () async {
      final saved = <String>['c-x'];
      var items = <AttentionItem>[];
      final store = PendingWorkStore(
        loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
        loadAttention: () async => page(items),
        loadDismissed: (_) => [...saved],
        saveDismissed: (_, ids) => saved
          ..clear()
          ..addAll(ids),
        currentUid: () => 'u1',
      );
      await store.refresh();
      expect(store.attentionConversationIds, {'c-x'});
      items = [_item('x2', conversationId: 'c-x')];
      await store.refresh();
      expect(store.attention.map((i) => i.id), ['x2']);
      expect(saved, isEmpty);
    });

    test('a 404 means the row is already gone', () async {
      final store = _store(_Calls(),
          attention: page([_item('x')]), dismiss: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)));
      await store.refresh();
      expect(await store.dismiss(store.attention.single), isTrue);
      expect(store.attention, isEmpty);
    });

    test('a read that started before the dismiss cannot bring the row back', () async {
      final read = Completer<ApiResult<AttentionItemsPage>>();
      var first = true;
      final store = PendingWorkStore(
        loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
        loadAttention: () {
          if (first) {
            first = false;
            return Future.value(page([_item('x')]));
          }
          return read.future;
        },
        dismiss: (_) async => const ApiSuccess(null),
      );
      await store.refresh();
      final refreshing = store.refresh();
      await store.dismiss(store.attention.single);
      read.complete(page([_item('x')]));
      await refreshing;
      expect(store.attention, isEmpty);
    });
  });
}
