// Notes-only retries use the ledger and preserve task/event state and failure reachability.
import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/pending_work.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import '../helpers/home_fixture_env.dart';

const notesKind = 'conversation_notes_failed_with_outputs';
AttentionItem attention(String id, {String kind = notesKind}) => AttentionItem(
      id: id,
      kind: kind,
      conversationId: 'conversation',
      retryable: true,
      seen: false,
      retryState: AttentionRetryState.none,
    );
PendingWorkSnapshot pending(bool enabled) => PendingWorkSnapshot(
      enabled: true,
      items: [],
      attentionUnseenCount: 0,
      homeProcessingToday: enabled,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() => Env.init(HomeFixtureEnv()));

  test('minimal wire contract and unknown kinds decode, retry POST carries item id and key', () async {
    final page = await api.getAttentionItems(send: (request) async {
      expect(Uri.parse(request.url).path, '/v1/attention-items');
      return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'item:/x',
                'kind': notesKind,
                'conversation_id': 'conversation',
                'retryable': true,
                'retry': {'state': 'none', 'operation_id': null}
              },
              {
                'id': 'future',
                'kind': 'future_kind',
                'conversation_id': 'future',
                'retryable': true,
                'retry': {'state': 'none', 'operation_id': null}
              }
            ]
          }),
          200);
    });
    final items = (page as ApiSuccess<AttentionItemsPage>).data.items;
    expect(items.first.canRetry, isTrue);
    expect(items.last.canRetry, isFalse);
    final result = await api.retryAttentionItem(items.first.id, idempotencyKey: 'same-key', send: (request) async {
      expect(request.method, 'POST');
      expect(request.url, endsWith('/v1/attention-items/item%3A%2Fx/retry'));
      expect(request.headers['Idempotency-Key'], 'same-key');
      return http.Response('{"operation_id":"op","state":"in_progress"}', 200);
    });
    expect((result as ApiSuccess<AttentionRetryResult>).data.operationId, 'op');
  });

  test('notes win conversation deduplication; unknown kinds never retry, including Retry all', () async {
    final sent = <String>[];
    var enabled = true;
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(pending(enabled)),
      loadAttention: () async => ApiSuccess(AttentionItemsPage(
          enabled: true,
          items: [
            attention('summary', kind: 'conversation_summary_failed'),
            attention('notes'),
            const AttentionItem(
                id: 'future',
                kind: 'future',
                conversationId: 'future',
                retryable: true,
                seen: false,
                retryState: AttentionRetryState.none),
          ],
          unseenCount: 0)),
      retry: (id, {required idempotencyKey}) async {
        sent.add(id);
        return ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.succeeded));
      },
      retryAll: ({required idempotencyKey}) async => throw StateError('Global retry must not touch unknown kinds'),
    );
    addTearDown(store.dispose);
    await store.refresh();
    expect(store.attention.map((i) => i.id), ['notes', 'future']);
    expect(await store.retry(store.attention.last), isFalse);
    await store.retryAll();
    expect(sent, ['notes']);
    expect(store.attention.map((i) => i.id), ['future']);
    expect(store.attentionConversationIds, contains('conversation'));
    // A stale GET must not resurrect the accepted notes retry.
    await store.refresh();
    expect(store.attention.where((i) => i.notesOnly), isEmpty);
    enabled = false;
    store.reset();
    await store.refresh();
    expect(store.attention.where((i) => i.notesOnly), isEmpty);
  });

  for (final response in [
    const ApiFailure<AttentionRetryResult>(ApiProblem(ApiProblemKind.rejected, statusCode: 409)),
    const ApiFailure<AttentionRetryResult>(ApiProblem(ApiProblemKind.transport)),
    const ApiSuccess(AttentionRetryResult(itemId: 'notes', state: AttentionRetryState.failed)),
  ]) {
    test('rejected/failed retry retains the item with an error: $response', () async {
      final store = PendingWorkStore(
        loadPending: () async => ApiSuccess(pending(true)),
        loadAttention: () async =>
            ApiSuccess(AttentionItemsPage(enabled: true, items: [attention('notes')], unseenCount: 0)),
        retry: (id, {required idempotencyKey}) async => response,
      );
      addTearDown(store.dispose);
      await store.refresh();
      expect(await store.retry(store.attention.single), isFalse);
      expect(store.attention.single.canRetry, isTrue);
      expect(store.retryErrors, contains('notes'));
    });
  }

  test('a pre-retry read cannot resurrect an older ledger generation', () async {
    final stale = Completer<ApiResult<AttentionItemsPage>>();
    var reads = 0;
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(pending(true)),
      loadAttention: () {
        reads++;
        if (reads == 2) {
          return stale.future;
        }
        return Future.value(ApiSuccess(AttentionItemsPage(enabled: true, items: [attention('notes')], unseenCount: 0)));
      },
      retry: (id, {required idempotencyKey}) async =>
          ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress, operationId: 'op')),
    );
    addTearDown(store.dispose);
    await store.refresh();
    final refresh = store.refresh();
    await store.retry(store.attention.single);
    stale.complete(ApiSuccess(AttentionItemsPage(enabled: true, items: [attention('old-generation')], unseenCount: 0)));
    await refresh;
    expect(store.attention, isEmpty);
    expect(store.attentionConversationIds, contains('conversation'));
  });

  test('a newly discovered notes generation becomes visible after an accepted retry', () async {
    var item = attention('notes');
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(pending(true)),
      loadAttention: () async => ApiSuccess(AttentionItemsPage(enabled: true, items: [item], unseenCount: 0)),
      retry: (id, {required idempotencyKey}) async =>
          ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress, operationId: 'op')),
    );
    addTearDown(store.dispose);
    await store.refresh();
    await store.retry(store.attention.single);
    item = attention('new-generation');
    await store.refresh();
    expect(store.attention.single.id, 'new-generation');
  });

  test('double taps and a late retry across account reset are fenced', () async {
    final result = Completer<ApiResult<AttentionRetryResult>>();
    var calls = 0;
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(pending(true)),
      loadAttention: () async =>
          ApiSuccess(AttentionItemsPage(enabled: true, items: [attention('notes')], unseenCount: 0)),
      retry: (id, {required idempotencyKey}) {
        calls++;
        return result.future;
      },
    );
    addTearDown(store.dispose);
    await store.refresh();
    final item = store.attention.single;
    final first = store.retry(item);
    expect(await store.retry(item), isFalse);
    expect(calls, 1);
    store.reset();
    result.complete(const ApiSuccess(AttentionRetryResult(itemId: 'notes', state: AttentionRetryState.succeeded)));
    expect(await first, isFalse);
    expect(store.attentionConversationIds, isEmpty);
  });
}
