import 'package:flutter/foundation.dart';

import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/pending_work.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';

/// The server's view of pending work and of work it gave up on, for the device catch-up card and the
/// bell. One shared instance; tests build their own with fakes.
///
/// A backend that predates the endpoints answers 404 (or `enabled: false`): the card then reads only
/// local state and the bell shows no attention items.
class PendingWorkStore extends ChangeNotifier {
  PendingWorkStore({
    Future<ApiResult<PendingWorkSnapshot>> Function()? loadPending,
    Future<ApiResult<AttentionItemsPage>> Function()? loadAttention,
    Future<ApiResult<AttentionRetryResult>> Function(String id, {required String idempotencyKey})? retry,
    Future<ApiResult<List<AttentionRetryResult>>> Function({required String idempotencyKey})? retryAll,
    Future<ApiResult<void>> Function(List<String> ids)? markSeen,
    String Function()? newKey,
  })  : _loadPending = loadPending ?? api.getPendingWork,
        _loadAttention = loadAttention ?? api.getAttentionItems,
        _retry = retry ?? api.retryAttentionItem,
        _retryAll = retryAll ?? api.retryAllAttentionItems,
        _markSeen = markSeen ?? api.markAttentionItemsSeen,
        _newKey = newKey ?? (() => const Uuid().v4());

  static PendingWorkStore instance = PendingWorkStore();

  final Future<ApiResult<PendingWorkSnapshot>> Function() _loadPending;
  final Future<ApiResult<AttentionItemsPage>> Function() _loadAttention;
  final Future<ApiResult<AttentionRetryResult>> Function(String id, {required String idempotencyKey}) _retry;
  final Future<ApiResult<List<AttentionRetryResult>>> Function({required String idempotencyKey}) _retryAll;
  final Future<ApiResult<void>> Function(List<String> ids) _markSeen;
  final String Function() _newKey;

  List<PendingWorkItem> _pending = const [];

  /// Server pending work the phone may not know about (another device, a filtered list, a lost
  /// event).
  List<PendingWorkItem> get pending => _pending;

  List<AttentionItem> _attention = const [];

  /// Unresolved work the server gave up on, newest first.
  List<AttentionItem> get attention => _attention;

  /// Lights Home's bell next to new recaps. Server read state, so the phone and the Mac agree.
  final ValueNotifier<bool> hasUnseenAttention = ValueNotifier(false);

  /// One key per item per failed attempt, so a double tap or a lost response replays the same claim.
  final Map<String, String> _retryKeys = {};
  String? _retryAllKey;

  int _generation = 0;

  /// Re-reads both server views. A failed read keeps the last good rows: a flaky network must not
  /// empty the bell or drop the card.
  Future<void> refresh() async {
    final generation = ++_generation;
    final results = await Future.wait<Object>([_loadPending(), _loadAttention()]);
    if (generation != _generation) return;
    final pending = results[0] as ApiResult<PendingWorkSnapshot>;
    final attention = results[1] as ApiResult<AttentionItemsPage>;
    switch (pending) {
      case ApiSuccess(:final data):
        _pending = data.enabled ? data.items : const [];
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        _pending = const [];
      case ApiFailure():
        break;
    }
    switch (attention) {
      case ApiSuccess(:final data):
        _setAttention(data.enabled ? data.items : const []);
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        _setAttention(const []);
      case ApiFailure():
        break;
    }
    notifyListeners();
  }

  void _setAttention(List<AttentionItem> items) {
    _attention = items;
    _retryKeys.removeWhere((id, _) => !items.any((i) => i.id == id));
    hasUnseenAttention.value = items.any((i) => !i.seen);
  }

  /// Retries one item. The server owns idempotency; the key only makes a replay recognizable.
  Future<bool> retry(AttentionItem item) async {
    if (!item.retryable || item.retryState == AttentionRetryState.inProgress) return false;
    final key = _retryKeys.putIfAbsent(item.id, _newKey);
    _replace(item.id, (i) => i.copyWith(retryState: AttentionRetryState.inProgress));
    final result = await _retry(item.id, idempotencyKey: key);
    switch (result) {
      case ApiSuccess(:final data):
        _replace(item.id, (i) => i.copyWith(retryState: data.state));
        return true;
      case ApiFailure():
        // A failed request may still have reached the server: the key is kept so the next tap
        // replays the same claim.
        _replace(item.id, (i) => i.copyWith(retryState: item.retryState));
        return false;
    }
  }

  /// Retries every retryable item once. Reuses its key until the server answers, so a second tap
  /// while the first is in flight, or after a lost response, cannot start a second paid run.
  Future<bool> retryAll() async {
    final key = _retryAllKey ??= _newKey();
    final marked = [
      for (final item in _attention)
        if (item.retryable && item.retryState == AttentionRetryState.none) item.id,
    ];
    for (final id in marked) {
      _replace(id, (i) => i.copyWith(retryState: AttentionRetryState.inProgress));
    }
    final result = await _retryAll(idempotencyKey: key);
    switch (result) {
      case ApiSuccess(:final data):
        _retryAllKey = null;
        for (final op in data) {
          _replace(op.itemId, (i) => i.copyWith(retryState: op.state));
        }
        return true;
      case ApiFailure():
        // The key is kept: the next Retry all replays this claim instead of starting another.
        for (final id in marked) {
          _replace(id, (i) => i.copyWith(retryState: AttentionRetryState.none));
        }
        return false;
    }
  }

  /// The bell was opened and these items were shown: dark on every device.
  Future<void> markSeen() async {
    final unseen = [
      for (final i in _attention)
        if (!i.seen) i.id,
    ];
    if (unseen.isEmpty) return;
    _attention = [for (final i in _attention) i.seen ? i : i.copyWith(seen: true)];
    hasUnseenAttention.value = false;
    notifyListeners();
    await _markSeen(unseen);
  }

  void _replace(String id, AttentionItem Function(AttentionItem) change) {
    if (!_attention.any((i) => i.id == id)) return;
    _attention = [for (final i in _attention) i.id == id ? change(i) : i];
    notifyListeners();
  }
}
