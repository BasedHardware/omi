import 'dart:async';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/gen/pending_work_wire.g.dart' as wire;
import 'package:omi/services/pending_work/pending_work_store.dart';

/// The one-row Home and the bell's Needs attention read one store; retries reuse one idempotency
/// key until the server answers.

AttentionItem _item(String id, {bool seen = false, bool retryable = true}) => AttentionItem(
      id: id,
      kind: 'conversation_summary_failed',
      conversationId: 'c-$id',
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

  test('every failed read restores old Home after a successful opt-in', () async {
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
      expect(store.homeProcessingToday, isFalse, reason: kind.name);
      store.dispose();
    }
  });

  test('thrown reads and account reset restore old placement', () async {
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
    expect(store.homeProcessingToday, isFalse);
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
}
