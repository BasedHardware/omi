import 'package:flutter/foundation.dart';

import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/pending_work.dart' as api;
import 'package:omi/backend/preferences.dart';
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
    Future<ApiResult<void>> Function(String id)? dismiss,
    List<String> Function(String uid)? loadDismissed,
    void Function(String uid, List<String> conversationIds)? saveDismissed,
    String Function()? currentUid,
    String Function()? newKey,
  })  : _loadPending = loadPending ?? api.getPendingWork,
        _loadAttention = loadAttention ?? api.getAttentionItems,
        _retry = retry ?? api.retryAttentionItem,
        _retryAll = retryAll ?? api.retryAllAttentionItems,
        _markSeen = markSeen ?? api.markAttentionItemsSeen,
        _dismiss = dismiss ?? api.dismissAttentionItem,
        _loadDismissed = loadDismissed ?? ((uid) => SharedPreferencesUtil().getStringList('$_dismissedKey.$uid')),
        _saveDismissed =
            saveDismissed ?? ((uid, ids) => SharedPreferencesUtil().saveStringList('$_dismissedKey.$uid', ids)),
        _currentUid = currentUid ?? (() => SharedPreferencesUtil().uid),
        _newKey = newKey ?? (() => const Uuid().v4());

  static PendingWorkStore instance = PendingWorkStore();

  final Future<ApiResult<PendingWorkSnapshot>> Function() _loadPending;
  final Future<ApiResult<AttentionItemsPage>> Function() _loadAttention;
  final Future<ApiResult<AttentionRetryResult>> Function(String id, {required String idempotencyKey}) _retry;
  final Future<ApiResult<List<AttentionRetryResult>>> Function({required String idempotencyKey}) _retryAll;
  final Future<ApiResult<void>> Function(List<String> ids) _markSeen;
  final Future<ApiResult<void>> Function(String id) _dismiss;
  final List<String> Function(String uid) _loadDismissed;
  final void Function(String uid, List<String> conversationIds) _saveDismissed;
  final String Function() _currentUid;
  final String Function() _newKey;

  List<PendingWorkItem> _pending = const [];

  /// Server pending work the phone may not know about (another device, a filtered list, a lost
  /// event).
  List<PendingWorkItem> get pending =>
      homeProcessingToday ? _pending.where((item) => item.homeStep != 'failed').toList() : _pending;

  /// Activity owns projected failures; catch-up/Home consumers exclude them.
  List<PendingWorkItem> get pendingForActivity => _pending;

  /// Server-driven Home placement kill switch, shared by Home and Activity.
  bool homeProcessingToday = false;

  /// Fence in-flight reads and forget the previous account on sign-out/switch.
  void reset() {
    _generation++;
    homeProcessingToday = false;
    _pending = const [];
    _setAttention(const []);
    _retryKeys.clear();
    _acceptedNotes.clear();
    _acceptedOperations.clear();
    _retrying.clear();
    retryErrors.clear();
    _session++;
    _retryAllKey = null;
    _seenFailedConversations.clear();
    // The next read loads the signed-in account's own list; nothing of the old one is kept or re-saved.
    _dismissedOwner = null;
    _dismissedSet = {};
    failedConversationsSeen.value++;
    _pendingAnswered = false;
    notifyListeners();
  }

  List<AttentionItem> _attention = const [];

  /// Unresolved work the server gave up on, newest first.
  List<AttentionItem> get attention {
    final byConversation = <String, AttentionItem>{};
    for (final item in _attention) {
      if (_acceptedNotes.containsValue(item.conversationId) || (item.notesOnly && !homeProcessingToday)) {
        continue;
      }
      final key = item.conversationId ?? item.id;
      if (!byConversation.containsKey(key) || (item.notesOnly && !byConversation[key]!.notesOnly)) {
        byConversation[key] = item;
      }
    }
    return byConversation.values.toList();
  }

  /// Successful notes retries also suppress stale projected failure rows.
  Set<String> get attentionConversationIds => {
        for (final item in attention)
          if (item.conversationId != null) item.conversationId!,
        ..._acceptedNotes.values,
        ..._dismissedConversations,
      };
  final Map<String, String> _acceptedNotes = {};

  /// A dismissed row's conversation must not come back as Activity's projected failure row, also
  /// after a relaunch. Kept on the device per account, newest last, bounded. A new attention item
  /// for the conversation (a new failure) takes it off the list.
  String? _dismissedOwner;
  Set<String> _dismissedSet = {};
  static const _maxDismissed = 500;
  static const _dismissedKey = 'dismissedAttentionConversations';

  Set<String> get _dismissedConversations {
    final owner = _currentUid();
    if (owner != _dismissedOwner) {
      _dismissedOwner = owner;
      _dismissedSet = owner.isEmpty ? {} : {..._loadDismissed(owner)};
    }
    return _dismissedSet;
  }

  void _saveDismissedConversations() {
    final owner = _dismissedOwner;
    if (owner == null || owner.isEmpty) return;
    final ids = _dismissedSet.toList();
    _saveDismissed(owner, ids.length > _maxDismissed ? ids.sublist(ids.length - _maxDismissed) : ids);
  }

  final Set<String> retryErrors = {};
  final Map<String, String?> _acceptedOperations = {};
  final Set<String> _retrying = {};
  int _session = 0;
  int _attentionRevision = 0;

  /// Lights Home's bell next to new recaps. Server read state, so the phone and the Mac agree.
  final ValueNotifier<bool> hasUnseenAttention = ValueNotifier(false);

  /// v3 conversations that failed and that Activity has shown, so the bell's attention dot lights
  /// once per failure (X5). Local: v3 failures have no server attention item yet.
  final Set<String> _seenFailedConversations = {};

  /// Bumps when [markFailedConversationsSeen] adds an id or a dismiss changes the hidden set, so the
  /// bell re-reads.
  final ValueNotifier<int> failedConversationsSeen = ValueNotifier(0);

  bool hasUnseenFailedConversation(Iterable<String> failedIds) =>
      failedIds.any((id) => !_seenFailedConversations.contains(id));

  void markFailedConversationsSeen(Iterable<String> ids) {
    final before = _seenFailedConversations.length;
    _seenFailedConversations.addAll(ids);
    if (_seenFailedConversations.length != before) failedConversationsSeen.value++;
  }

  /// One key per item per failed attempt, so a double tap or a lost response replays the same claim.
  final Map<String, String> _retryKeys = {};
  String? _retryAllKey;

  int _generation = 0;

  /// True once this account's pending read has answered; until then a failed read keeps old Home.
  bool _pendingAnswered = false;

  /// Re-reads both server views. A failed read keeps the last good rows: a flaky network must not
  /// empty the bell or drop the card.
  Future<void> refresh() async {
    final generation = ++_generation;
    final attentionRevision = _attentionRevision;
    final results = await Future.wait<Object>([_read(_loadPending), _read(_loadAttention)]);
    if (generation != _generation) return;
    final pending = results[0] as ApiResult<PendingWorkSnapshot>;
    final attention = results[1] as ApiResult<AttentionItemsPage>;
    switch (pending) {
      case ApiSuccess(:final data):
        _pending = data.enabled ? data.items : const [];
        homeProcessingToday = data.enabled && data.homeProcessingToday;
        _pendingAnswered = true;
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        _pending = const [];
        homeProcessingToday = false;
      case ApiFailure():
        // A flaky read keeps the last good answer (X17): dropping the flag would empty Activity's
        // attention and processing lists, which it gates. With no answer yet, old Home stays.
        if (!_pendingAnswered) homeProcessingToday = false;
    }
    if (attentionRevision == _attentionRevision) {
      switch (attention) {
        case ApiSuccess(:final data):
          _setAttention(data.enabled ? data.items : const []);
        case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
          _setAttention(const []);
        case ApiFailure():
          break;
      }
    }
    notifyListeners();
  }

  Future<ApiResult<T>> _read<T>(Future<ApiResult<T>> Function() load) async {
    try {
      return await load();
    } catch (_) {
      return ApiFailure<T>(const ApiProblem(ApiProblemKind.transport));
    }
  }

  void _setAttention(List<AttentionItem> items) {
    _attention = items;
    final dismissed = _dismissedConversations;
    final before = dismissed.length;
    dismissed.removeWhere((id) => items.any((i) => i.conversationId == id));
    if (dismissed.length != before) _saveDismissedConversations();
    _acceptedNotes.removeWhere((id, conversation) =>
        items.any((item) => item.notesOnly && item.conversationId == conversation && item.id != id));
    _acceptedNotes.removeWhere((id, _) => items.any((i) =>
        i.id == id &&
        i.retryState == AttentionRetryState.failed &&
        i.operationId != null &&
        i.operationId == _acceptedOperations[id]));
    _acceptedOperations.removeWhere((id, _) => !_acceptedNotes.containsKey(id));
    _retryKeys.removeWhere((id, _) => !items.any((i) => i.id == id));
    hasUnseenAttention.value = attention.any((i) => !i.seen);
  }

  /// Retries one item. The server owns idempotency; the key only makes a replay recognizable.
  Future<bool> retry(AttentionItem item) async {
    if (!item.canRetry ||
        _retrying.contains(item.id) ||
        _acceptedNotes.containsValue(item.conversationId) ||
        (item.notesOnly && !homeProcessingToday)) {
      return false;
    }
    final session = _session;
    _attentionRevision++;
    _retrying.add(item.id);
    retryErrors.remove(item.id);
    final key = _retryKeys.putIfAbsent(item.id, _newKey);
    _replace(item.id, (i) => i.copyWith(retryState: AttentionRetryState.inProgress));
    final result = await _read(() => _retry(item.id, idempotencyKey: key));
    if (session != _session) return false;
    _retrying.remove(item.id);
    switch (result) {
      case ApiSuccess(:final data):
        // A confirmed failed attempt is terminal; the next user action starts
        // a fresh claim. Transport failures below keep their ambiguous key.
        if (data.state == AttentionRetryState.failed) {
          _retryKeys.remove(item.id);
          retryErrors.add(item.id);
        } else if (item.notesOnly &&
            (data.state == AttentionRetryState.inProgress || data.state == AttentionRetryState.succeeded)) {
          _acceptedNotes[item.id] = item.conversationId ?? item.id;
          _acceptedOperations[item.id] = data.operationId;
        }
        _replace(item.id, (i) => i.copyWith(retryState: data.state));
        return data.state != AttentionRetryState.failed;
      case ApiFailure():
        // A failed request may still have reached the server: the key is kept so the next tap
        // replays the same claim.
        retryErrors.add(item.id);
        _replace(item.id, (i) => i.copyWith(retryState: item.retryState));
        return false;
    }
  }

  /// Retries every retryable item once. Reuses its key until the server answers, so a second tap
  /// while the first is in flight, or after a lost response, cannot start a second paid run.
  Future<bool> retryAll() async {
    // Never let the global endpoint retry a kind this client does not understand.
    if (_attention.any((item) => item.kind != 'conversation_summary_failed')) {
      final results = await Future.wait(attention.where((item) => item.canRetry).map(retry));
      return results.every((ok) => ok);
    }
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
      for (final i in attention)
        if (!i.seen) i.id,
    ];
    if (unseen.isEmpty) return;
    _attention = [for (final i in _attention) unseen.contains(i.id) ? i.copyWith(seen: true) : i];
    hasUnseenAttention.value = false;
    notifyListeners();
    await _markSeen(unseen);
  }

  /// Removes one item at once and tells the server. A failed request puts the row back with the
  /// same quiet error line as a failed retry; a 404 means it is already gone.
  Future<bool> dismiss(AttentionItem item) async {
    final index = _attention.indexWhere((i) => i.id == item.id);
    if (index < 0) return false;
    final session = _session;
    _attentionRevision++;
    final removed = _attention[index];
    final retryKey = _retryKeys[item.id];
    retryErrors.remove(item.id);
    _setAttention([
      for (final i in _attention)
        if (i.id != item.id) i
    ]);
    final conversationId = removed.conversationId;
    // Another live item for the same conversation keeps it visible: only a conversation with no
    // remaining row is hidden from the failure projection.
    final suppressing = conversationId != null &&
        !_attention.any((i) => i.conversationId == conversationId) &&
        _dismissedConversations.add(conversationId);
    if (suppressing) _saveDismissedConversations();
    // The bell re-reads its failed-conversation dot, which now skips this conversation.
    failedConversationsSeen.value++;
    notifyListeners();
    final result = await _read(() => _dismiss(item.id));
    if (session != _session) return false;
    switch (result) {
      case ApiSuccess():
        return true;
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        return true;
      case ApiFailure():
        if (suppressing) {
          _dismissedConversations.remove(conversationId);
          _saveDismissedConversations();
          failedConversationsSeen.value++;
        }
        if (!_attention.any((i) => i.id == item.id)) {
          _attentionRevision++;
          _setAttention([..._attention]..insert(index.clamp(0, _attention.length), removed));
          // An ambiguous earlier retry keeps its claim, so the next Try Again cannot start a second run.
          if (retryKey != null) _retryKeys[item.id] = retryKey;
        }
        retryErrors.add(item.id);
        notifyListeners();
        return false;
    }
  }

  void _replace(String id, AttentionItem Function(AttentionItem) change) {
    if (!_attention.any((i) => i.id == id)) return;
    _attention = [for (final i in _attention) i.id == id ? change(i) : i];
    notifyListeners();
  }
}
