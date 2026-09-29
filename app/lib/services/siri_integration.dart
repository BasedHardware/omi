import 'dart:async';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/analytics/registry/events.g.dart' as siri_events;
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Small test seam for the conversation capture path used by Siri's foreground
/// Start/Stop actions. Production resolves these callbacks from CaptureProvider.
typedef SiriListeningCapture = ({
  Future<void> Function() start,
  Future<bool> Function() stop,
  String? Function() source,
  bool Function() deviceConnected,
  bool Function() phoneBatchRecording,
  bool Function() deviceBatchRecording,
  bool Function() phonePaused,
});

typedef SiriMemoryPageFetcher = Future<GetMemoriesResult> Function(
    {required int limit, required int offset, String? cursor});
typedef SiriTaskPageFetcher = Future<ApiResult<ActionItemsResponse>> Function(
    {required int limit, required int offset, required bool completed});
typedef SiriConversationPageFetcher = Future<ApiResult<List<ServerConversation>>> Function({
  required int limit,
  required int offset,
  required DateTime startDate,
});

class _PendingSiriReconcile {
  _PendingSiriReconcile(this.type, this.apply);
  final String type;
  final Future<void> Function() apply;
}

/// The same owner-visible scope is used by both incremental writes and full
/// snapshot reconciliation. A row leaving this scope must be deleted from the
/// native index, even when the account's indexing preference is off.
bool siriMemoryIsIndexable(Memory row, DateTime now, {String? owner}) =>
    row.id.isNotEmpty &&
    (owner == null || row.uid == owner) &&
    !row.deleted &&
    !row.isDismissed &&
    !row.isLocked &&
    row.siriVisibilityValid &&
    row.siriTierValid &&
    (row.layer == null || row.layer == MemoryLayer.shortTerm || row.layer == MemoryLayer.longTerm) &&
    (row.siriExpiryAt == null || row.siriExpiryAt!.isAfter(now)) &&
    (row.ledgerStatus == null || row.ledgerStatus == 'active') &&
    (row.supersededBy == null || row.supersededBy!.isEmpty) &&
    row.userReview != false;

bool siriConversationIsIndexable(ServerConversation row, DateTime now) =>
    row.id.isNotEmpty &&
    row.status == ConversationStatus.completed &&
    !row.discarded &&
    !row.deleted &&
    !row.isLocked &&
    row.siriVisibilityValid &&
    (row.startedAt ?? row.createdAt).isAfter(now.subtract(const Duration(days: 180)));

bool siriTaskIsIndexable(ActionItemWithMetadata row, DateTime now) =>
    row.id.isNotEmpty &&
    !row.isLocked &&
    (row.status == 'active' || row.status == 'completed') &&
    (row.supersededBy == null || row.supersededBy!.isEmpty) &&
    (!row.completed || (row.completedAt?.isAfter(now.subtract(const Duration(days: 30))) ?? false));

/// Retry indefinitely at a capped interval: native repair persists the owner
/// cleanup marker, and this single timer gives a still-running app a way to
/// finish the delete without waiting for another launch.
Duration siriRemovalRetryDelay(Duration base, int attempt) =>
    Duration(milliseconds: (base.inMilliseconds * (1 << attempt.clamp(0, 8))).clamp(1, 300000));

/// The native index receives projections only after Dart's authoritative state
/// has accepted a fetch or mutation. All methods are inert on Android.
class SiriIntegration extends SiriEventsApi {
  SiriIntegration._()
      : _host = SiriIndexApi(),
        _isIOS = Platform.isIOS,
        _testSessionConfig = null,
        _testListeningCapture = null,
        _testMemoryPageFetcher = null,
        _testTaskPageFetcher = null,
        _testConversationPageFetcher = null,
        _prepareTimeout = const Duration(milliseconds: 1500),
        _nativeTimeout = const Duration(seconds: 12),
        _indexCooldown = const Duration(seconds: 30),
        _retryBase = const Duration(seconds: 1),
        _delay = Future<void>.delayed;

  /// Inject a Pigeon host for hermetic projection and account fencing tests.
  SiriIntegration.forTest(
    SiriIndexApi host,
    String uid, {
    SiriSessionConfig Function(User, IdTokenResult, int)? sessionConfig,
    SiriListeningCapture? listeningCapture,
    SiriMemoryPageFetcher? memoryPageFetcher,
    SiriTaskPageFetcher? taskPageFetcher,
    SiriConversationPageFetcher? conversationPageFetcher,
    Duration prepareTimeout = const Duration(milliseconds: 1500),
    Duration nativeTimeout = const Duration(seconds: 12),
    Duration indexCooldown = const Duration(seconds: 30),
    Duration retryBase = const Duration(milliseconds: 20),
    Future<void> Function(Duration)? delay,
    bool coldStart = false,
  })  : _host = host,
        _isIOS = true,
        _testSessionConfig = sessionConfig,
        _testListeningCapture = listeningCapture,
        _testMemoryPageFetcher = memoryPageFetcher,
        _testTaskPageFetcher = taskPageFetcher,
        _testConversationPageFetcher = conversationPageFetcher,
        _prepareTimeout = prepareTimeout,
        _nativeTimeout = nativeTimeout,
        _indexCooldown = indexCooldown,
        _retryBase = retryBase,
        _delay = delay ?? Future<void>.delayed,
        _uid = coldStart ? null : uid,
        _nativeGeneration = coldStart ? null : 0;
  static final instance = SiriIntegration._();
  @visibleForTesting
  static SiriIntegration? testInstance;
  static SiriIntegration get current => testInstance ?? instance;
  final SiriIndexApi _host;
  final bool _isIOS;
  final SiriSessionConfig Function(User, IdTokenResult, int)? _testSessionConfig;
  final SiriListeningCapture? _testListeningCapture;
  final SiriMemoryPageFetcher? _testMemoryPageFetcher;
  final SiriTaskPageFetcher? _testTaskPageFetcher;
  final SiriConversationPageFetcher? _testConversationPageFetcher;
  final Duration _prepareTimeout;
  final Duration _nativeTimeout;
  final Duration _indexCooldown;
  final Duration _retryBase;
  final Future<void> Function(Duration) _delay;
  void installEvents() {
    if (_isIOS) SiriEventsApi.setUp(this);
  }

  int _accountGeneration = 0;
  int? _nativeGeneration;
  Future<void> _nativeTail = Future<void>.value();
  Future<void> _queuedIndexTail = Future<void>.value();
  DateTime? _indexSuspendedUntil;
  Timer? _removalRetry;
  int _retryAttempt = 0;
  static const _maxPendingRemovalIds = 256;
  int _projectionEpoch = 0;
  int _minimumSourceEpoch = 0;
  bool _repairRequired = false;
  final Map<String, _PendingSiriReconcile> _pendingReconciles = {};
  final Map<String, Map<String, int>> _eligibilityFence = {
    'memory': <String, int>{},
    'conversation': <String, int>{},
    'task': <String, int>{},
  };
  final Map<String, Set<String>> _pendingRemovals = {
    'memory': <String>{},
    'conversation': <String>{},
    'task': <String>{},
  };
  final Map<String, Set<String>> _suppressedIds = {
    'memory': <String>{},
    'conversation': <String>{},
    'task': <String>{},
  };
  String? _uid;
  String? _ownerWideRefreshUid;
  DateTime? _ownerWideRefreshAt;

  Future<T> _nativeOperation<T>(Future<T> Function() operation, {bool indexWork = false}) {
    final result = _nativeTail.then((_) async {
      if (indexWork && (_indexSuspendedUntil?.isAfter(DateTime.now()) ?? false)) {
        throw TimeoutException('Siri index is cooling down after a native timeout');
      }
      try {
        return await operation().timeout(_nativeTimeout);
      } on TimeoutException {
        if (indexWork) _indexSuspendedUntil = DateTime.now().add(_indexCooldown);
        rethrow;
      }
    });
    _nativeTail = result.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return result;
  }

  /// Submit projections in UI order without making the UI wait for Spotlight.
  /// The owner is captured at submission, so an old account's queued rows can
  /// never be projected into a newly bound account.
  Future<void> _enqueueIndex(Future<void> Function(SiriIntegration) work) {
    if (!_isIOS || _uid == null) return Future<void>.value();
    final uid = _uid;
    final generation = _accountGeneration;
    _queuedIndexTail = _queuedIndexTail.then((_) async {
      if (_uid != uid || _accountGeneration != generation) return;
      await work(this);
    }).catchError((Object error) {
      Logger.debug('Siri background index failed: $error');
    });
    return _queuedIndexTail;
  }

  void queueIndex(Future<void> Function(SiriIntegration) work) {
    unawaited(_enqueueIndex(work));
  }

  void _clearPendingRemovals() {
    _removalRetry?.cancel();
    _removalRetry = null;
    for (final ids in _pendingRemovals.values) {
      ids.clear();
    }
    _pendingReconciles.clear();
    _repairRequired = false;
    _retryAttempt = 0;
  }

  bool _currentOwner(String uid, int generation) => _uid == uid && _accountGeneration == generation;

  int _nextEpoch() => ++_projectionEpoch;

  void _fenceIneligible(String type, Iterable<String> ids, int epoch) {
    if (_repairRequired || _uid == null) return;
    for (final id in ids.where((id) => id.isNotEmpty)) {
      final fence = _eligibilityFence[type]![id];
      if (fence == null || epoch >= fence) _eligibilityFence[type]![id] = epoch;
    }
    _checkFenceBudget();
  }

  void _checkFenceBudget() {
    if (_repairRequired || _uid == null) return;
    final count = _pendingRemovals.values.fold<int>(0, (n, ids) => n + ids.length) +
        _suppressedIds.values.fold<int>(0, (n, ids) => n + ids.length) +
        _eligibilityFence.values.fold<int>(0, (n, ids) => n + ids.length);
    if (count <= _maxPendingRemovalIds) return;
    _repairRequired = true;
    for (final ids in _pendingRemovals.values) {
      ids.clear();
    }
    for (final ids in _suppressedIds.values) {
      ids.clear();
    }
    for (final ids in _eligibilityFence.values) {
      ids.clear();
    }
    _pendingReconciles.clear();
    final uid = _uid!;
    final generation = _accountGeneration;
    queueIndex((siri) => siri._flushPendingWork(uid, generation));
  }

  bool _allowsRow(String type, String id, int sourceEpoch) {
    if (_repairRequired || _suppressedIds[type]!.contains(id) || sourceEpoch < _minimumSourceEpoch) return false;
    final fence = _eligibilityFence[type]![id];
    if (fence != null && sourceEpoch <= fence) return false;
    if (fence != null) _eligibilityFence[type]!.remove(id);
    _pendingRemovals[type]!.remove(id);
    return true;
  }

  void _retryLater(String uid, int generation) {
    _retryAttempt = (_retryAttempt + 1).clamp(0, 8);
    _scheduleRemovalRetry(uid, generation);
  }

  void _scheduleRemovalRetry(String uid, int generation) {
    if (_removalRetry != null || _uid != uid || _accountGeneration != generation) return;
    final remaining = _indexSuspendedUntil?.difference(DateTime.now()) ?? Duration.zero;
    // A failed attempt owns one timer; its callback clears the slot before
    // queueing the next attempt, so prolonged outages cannot stack retries.
    final backoff = siriRemovalRetryDelay(_retryBase, _retryAttempt);
    _removalRetry = Timer(remaining > backoff ? remaining : backoff, () {
      _removalRetry = null;
      if (_uid == uid && _accountGeneration == generation) {
        queueIndex((siri) => siri._flushPendingWork(uid, generation));
      }
    });
  }

  Future<void> _flushPendingWork(String uid, int generation) async {
    if (_repairRequired) {
      try {
        await _nativeOperation(() => _host.repairOwnerIndex(uid), indexWork: true);
        if (!_currentOwner(uid, generation)) return;
        _repairRequired = false;
        _minimumSourceEpoch = _nextEpoch();
        for (final ids in _pendingRemovals.values) {
          ids.clear();
        }
        for (final ids in _suppressedIds.values) {
          ids.clear();
        }
        for (final ids in _eligibilityFence.values) {
          ids.clear();
        }
        _pendingReconciles.clear();
        _retryAttempt = 0;
        unawaited(refreshOwnerWideIndex());
      } catch (error) {
        Logger.debug('Siri owner repair failed: $error');
        _retryLater(uid, generation);
      }
      return;
    }
    await _flushPendingRemovals(uid, generation);
    if (_pendingRemovals.values.any((ids) => ids.isNotEmpty)) return;
    for (final pending in _pendingReconciles.values.toList()) {
      if (!_currentOwner(uid, generation)) return;
      if (!identical(_pendingReconciles[pending.type], pending)) continue;
      try {
        await _nativeOperation(() => pending.apply(), indexWork: true);
        if (identical(_pendingReconciles[pending.type], pending)) _pendingReconciles.remove(pending.type);
        _retryAttempt = 0;
      } catch (error) {
        Logger.debug('Siri ${pending.type} reconciliation failed: $error');
        _retryLater(uid, generation);
        return;
      }
    }
  }

  Future<void> _flushPendingRemovals(String uid, int generation) async {
    if (_uid != uid || _accountGeneration != generation) return;
    for (final entry in _pendingRemovals.entries) {
      if (entry.value.isEmpty) continue;
      try {
        await _nativeOperation(() async {
          if (_uid != uid || _accountGeneration != generation) return;
          final ids = entry.value.toList();
          if (ids.isEmpty) return;
          await _host.deleteEntities(uid, entry.key, ids);
          if (_uid == uid && _accountGeneration == generation) entry.value.removeAll(ids);
        }, indexWork: true);
      } catch (error) {
        Logger.debug('Siri required removal failed: $error');
        _retryLater(uid, generation);
        return;
      }
    }
  }

  Future<void> _removeRequired(String uid, int generation, String type, Iterable<String> ids) async {
    if (_uid != uid || _accountGeneration != generation) return;
    if (_repairRequired) return;
    _pendingRemovals[type]!.addAll(ids.where((id) => id.isNotEmpty));
    _checkFenceBudget();
    await _flushPendingWork(uid, generation);
  }

  void queueUpsertMemories(List<Memory> rows, {bool restoreDeleted = false}) {
    final frozen = List<Memory>.of(rows);
    final epoch = _nextEpoch();
    final now = DateTime.now();
    _fenceIneligible(
        'memory',
        frozen.where((row) => row.uid == _uid && !siriMemoryIsIndexable(row, now, owner: _uid)).map((row) => row.id),
        epoch);
    if (restoreDeleted) _suppressedIds['memory']!.removeAll(frozen.map((row) => row.id));
    queueIndex((siri) async {
      if (restoreDeleted) siri._pendingRemovals['memory']!.removeAll(frozen.map((row) => row.id));
      await siri.upsertMemories(frozen, sourceEpoch: epoch);
    });
  }

  void queueReconcileMemories(List<Memory> rows) {
    final frozen = List<Memory>.of(rows);
    final epoch = _nextEpoch();
    queueIndex((siri) => siri.reconcileMemories(frozen, sourceEpoch: epoch));
  }

  void queueUpsertTasks(List<ActionItemWithMetadata> rows, {bool restoreDeleted = false}) {
    final frozen = List<ActionItemWithMetadata>.of(rows);
    final epoch = _nextEpoch();
    _fenceIneligible(
        'task', frozen.where((row) => !siriTaskIsIndexable(row, DateTime.now())).map((row) => row.id), epoch);
    if (restoreDeleted) _suppressedIds['task']!.removeAll(frozen.map((row) => row.id));
    queueIndex((siri) async {
      if (restoreDeleted) siri._pendingRemovals['task']!.removeAll(frozen.map((row) => row.id));
      await siri.upsertTasks(frozen, sourceEpoch: epoch);
    });
  }

  void queueReconcileTasks(List<ActionItemWithMetadata> rows, {required bool includeCompleted}) {
    final frozen = List<ActionItemWithMetadata>.of(rows);
    final epoch = _nextEpoch();
    queueIndex((siri) => siri.reconcileTasks(frozen, includeCompleted: includeCompleted, sourceEpoch: epoch));
  }

  void queueReconcileConversations(List<ServerConversation> rows, {DateTime? coveredAfter}) {
    final frozen = List<ServerConversation>.of(rows);
    final epoch = _nextEpoch();
    queueIndex((siri) => siri.reconcileConversations(frozen, coveredAfter: coveredAfter, sourceEpoch: epoch));
  }

  void queueDelete(String type, String id) {
    final epoch = _nextEpoch();
    if (!_repairRequired) _suppressedIds[type]?.add(id);
    _checkFenceBudget();
    queueIndex((siri) => epoch < siri._minimumSourceEpoch ? Future<void>.value() : siri.delete(type, id));
  }

  void queueDeleteMany(String type, List<String> ids, {String? expectedUid}) {
    if (expectedUid != null && expectedUid != _uid) return;
    final frozen = List<String>.of(ids);
    final epoch = _nextEpoch();
    if (!_repairRequired) _suppressedIds[type]?.addAll(frozen);
    _checkFenceBudget();
    queueIndex((siri) => epoch < siri._minimumSourceEpoch
        ? Future<void>.value()
        : siri.deleteMany(type, frozen, expectedUid: expectedUid));
  }

  void queueRefreshAuthoritativeTasks({String? expectedUid}) {
    unawaited(refreshAuthoritativeTasks(expectedUid: expectedUid).catchError((Object error) {
      Logger.debug('Siri task refresh failed: $error');
    }));
  }

  @visibleForTesting
  Future<void> drainIndexForTest() => _queuedIndexTail;

  /// This privacy fence bypasses the index queue: a stuck Spotlight operation
  /// must not delay Firebase sign-out or leave engine-free Siri authorized.
  Future<void> prepareForSignOut() async {
    if (!_isIOS) return;
    ++_accountGeneration;
    _uid = null;
    _nativeGeneration = null;
    for (final ids in _suppressedIds.values) {
      ids.clear();
    }
    for (final ids in _eligibilityFence.values) {
      ids.clear();
    }
    _minimumSourceEpoch = _nextEpoch();
    _clearPendingRemovals();
    await _host.prepareForSignOut().timeout(_prepareTimeout);
  }

  /// Synchronous provider callbacks keep their immediate UI update. Their
  /// index work is owned by this ordered Future chain and each native call is
  /// awaited before the next callback's projection starts.
  void queueUpsertConversations(List<ServerConversation> rows, {String? expectedUid, bool restoreDeleted = false}) {
    if (expectedUid != null && expectedUid != _uid) return;
    final frozenRows = List<ServerConversation>.of(rows);
    final epoch = _nextEpoch();
    _fenceIneligible('conversation',
        frozenRows.where((row) => !siriConversationIsIndexable(row, DateTime.now())).map((row) => row.id), epoch);
    if (restoreDeleted) _suppressedIds['conversation']!.removeAll(frozenRows.map((row) => row.id));
    queueIndex((siri) async {
      if (restoreDeleted) siri._pendingRemovals['conversation']!.removeAll(frozenRows.map((row) => row.id));
      await siri.upsertConversations(frozenRows, expectedUid: expectedUid, sourceEpoch: epoch);
    });
  }

  Future<void> accountChanged(User? user) async {
    if (!_isIOS) return;
    final generation = ++_accountGeneration;
    final uid = user?.uid;
    if (uid != _uid) {
      _clearPendingRemovals();
      for (final ids in _suppressedIds.values) {
        ids.clear();
      }
      for (final ids in _eligibilityFence.values) {
        ids.clear();
      }
      _minimumSourceEpoch = _nextEpoch();
    } else {
      if (_pendingReconciles.isNotEmpty) _ownerWideRefreshAt = null;
      _pendingReconciles.clear();
      _removalRetry?.cancel();
      _removalRetry = null;
      if (uid != null && (_repairRequired || _pendingRemovals.values.any((ids) => ids.isNotEmpty))) {
        _scheduleRemovalRetry(uid, generation);
      }
    }
    if (uid != null && _nativeGeneration == null) {
      try {
        final savedGeneration = await _nativeOperation(() => _host.generationForOwner(uid));
        if (generation != _accountGeneration) return;
        if (savedGeneration != null) {
          _uid = uid;
          _nativeGeneration = savedGeneration;
        }
      } catch (error) {
        Logger.debug('Siri owner resume failed: $error');
        return; // An uncertain owner must not trigger a destructive startup wipe.
      }
    }
    if (uid == null || uid != _uid || _nativeGeneration == null) {
      _uid = null;
      _nativeGeneration = null;
      try {
        final nativeGeneration = await _nativeOperation(_host.wipe);
        if (generation == _accountGeneration) _nativeGeneration = nativeGeneration;
      } catch (error) {
        Logger.debug('Siri wipe failed: $error');
        return; // Never bind another account while the old snapshot remains.
      }
    }
    if (uid == null || generation != _accountGeneration) return;
    _uid = uid;
    await refreshSession(user!);
    _scheduleOwnerWideRefresh(uid, generation);
  }

  void _scheduleOwnerWideRefresh(String uid, int generation) {
    final now = DateTime.now();
    if (_ownerWideRefreshUid == uid &&
        _ownerWideRefreshAt != null &&
        now.difference(_ownerWideRefreshAt!) < const Duration(days: 1)) {
      return;
    }
    _ownerWideRefreshUid = uid;
    _ownerWideRefreshAt = now;
    Timer(const Duration(seconds: 2), () async {
      try {
        if (_uid != uid || _accountGeneration != generation || !await isEnabled()) return;
        await refreshOwnerWideIndex();
      } catch (error) {
        Logger.debug('Siri deferred owner-wide refresh failed: $error');
      }
    });
  }

  /// Runs outside UI pagination and only reconciles an authoritative, complete
  /// traversal. A capped, truncated, decoded-partial, or failed page is additive.
  Future<void> refreshOwnerWideIndex() async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    await _refreshOwnerWideTasks(uid, generation);
    if (_uid != uid || generation != _accountGeneration) return;
    await _refreshOwnerWideConversations(uid, generation);
    if (_uid != uid || generation != _accountGeneration) return;
    await refreshAuthoritativeMemories();
  }

  /// A confirmed external task batch (for example Apple Reminders sync) can
  /// change rows beyond the currently visible UI page.
  Future<void> refreshAuthoritativeTasks({String? expectedUid}) async {
    final uid = _uid;
    if (!_isIOS || uid == null || (expectedUid != null && uid != expectedUid)) return;
    await _refreshOwnerWideTasks(uid, _accountGeneration);
  }

  Future<void> _refreshOwnerWideTasks(String uid, int generation) async {
    final sourceEpoch = _nextEpoch();
    const limit = 100;
    const maxPages = 50;
    final rows = <ActionItemWithMetadata>[];
    var complete = true;
    for (final completed in [false, true]) {
      var sectionComplete = false;
      for (var page = 0; page < maxPages; page++) {
        ApiResult<ActionItemsResponse> result;
        try {
          result = await (_testTaskPageFetcher?.call(limit: limit, offset: page * limit, completed: completed) ??
                  ActionItemsApi(
                    baseUrl: Env.apiBaseUrl ?? '',
                  ).list(limit: limit, offset: page * limit, completed: completed))
              .timeout(const Duration(seconds: 10));
        } catch (error) {
          Logger.debug('Siri task traversal failed: $error');
          break;
        }
        if (_uid != uid || generation != _accountGeneration) return;
        if (result is! ApiSuccess<ActionItemsResponse>) break;
        final data = result.data;
        if (result.rejectedRows > 0 || result.truncated || data.truncated) break;
        rows.addAll(data.actionItems);
        if (!data.hasMore) {
          sectionComplete = true;
          break;
        }
      }
      complete = complete && sectionComplete;
    }
    if (_uid != uid || generation != _accountGeneration) return;
    if (complete) {
      await _enqueueIndex((siri) => siri.reconcileTasks(rows, includeCompleted: true, sourceEpoch: sourceEpoch));
    } else if (rows.isNotEmpty) {
      await _enqueueIndex((siri) => siri.upsertTasks(rows, sourceEpoch: sourceEpoch));
    }
  }

  Future<void> _refreshOwnerWideConversations(String uid, int generation) async {
    final sourceEpoch = _nextEpoch();
    const limit = 100;
    const maxPages = 50;
    const maxEligible = 2000;
    final cutoff = DateTime.now().subtract(const Duration(days: 180));
    final rows = <ServerConversation>[];
    var complete = false;
    for (var page = 0; page < maxPages; page++) {
      ApiResult<List<ServerConversation>> result;
      try {
        Future<ApiResult<List<ServerConversation>>> fetch() =>
            _testConversationPageFetcher?.call(limit: limit, offset: page * limit, startDate: cutoff) ??
            ConversationApi(baseUrl: Env.apiBaseUrl ?? '').list(
              limit: limit,
              offset: page * limit,
              statuses: const [ConversationStatus.completed],
              startDate: cutoff,
            );
        result = await fetch().timeout(const Duration(seconds: 10));
        if (result is ApiFailure<List<ServerConversation>> && result.problem.kind == ApiProblemKind.rateLimited) {
          await _delay(result.problem.retryAfter ?? const Duration(seconds: 2));
          if (_uid != uid || generation != _accountGeneration) return;
          result = await fetch().timeout(const Duration(seconds: 10));
        }
      } catch (error) {
        Logger.debug('Siri conversation traversal failed: $error');
        break;
      }
      if (_uid != uid || generation != _accountGeneration) return;
      if (result is! ApiSuccess<List<ServerConversation>>) break;
      if (result.rejectedRows > 0 || result.truncated) break;
      rows.addAll(result.data);
      if (rows.where((row) => siriConversationIsIndexable(row, DateTime.now())).length >= maxEligible) break;
      if (result.data.length < limit) {
        complete = true;
        break;
      }
    }
    if (_uid != uid || generation != _accountGeneration) return;
    if (complete) {
      await _enqueueIndex((siri) => siri.reconcileConversations(rows, coveredAfter: cutoff, sourceEpoch: sourceEpoch));
    } else if (rows.isNotEmpty) {
      await _enqueueIndex((siri) => siri.upsertConversations(rows, sourceEpoch: sourceEpoch));
    }
  }

  Future<void> refreshSession(User user) async {
    if (!_isIOS) return;
    if (user.uid != _uid) {
      await accountChanged(user);
      return;
    }
    final generation = _accountGeneration;
    final nativeGeneration = _nativeGeneration;
    if (nativeGeneration == null) return;
    try {
      final tokenResult = await user.getIdTokenResult();
      final token = tokenResult.token;
      if (generation != _accountGeneration || user.uid != _uid) return;
      final config = _testSessionConfig?.call(user, tokenResult, nativeGeneration) ??
          (() {
            final platform = PlatformManager.instance;
            return SiriSessionConfig(
              uid: user.uid,
              generation: nativeGeneration,
              baseUrl: Env.apiBaseUrl ?? '',
              profile: Env.profile.name,
              appVersion: platform.appVersion,
              appBuild: platform.appBuild,
              deviceIdHash: platform.deviceIdHash,
              token: token,
              tokenExpiresAtMs: tokenResult.expirationTime?.millisecondsSinceEpoch,
            );
          })();
      await _nativeOperation(() async {
        if (generation != _accountGeneration || user.uid != _uid || nativeGeneration != _nativeGeneration) return;
        await _host.publishSessionConfig(config);
      });
      if (generation == _accountGeneration && user.uid == _uid) await _flushTelemetry();
    } catch (error) {
      Logger.debug('Siri session mirror failed: $error');
    }
  }

  Future<void> upsertConversations(List<ServerConversation> rows, {String? expectedUid, int? sourceEpoch}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null || (expectedUid != null && uid != expectedUid)) return;
    final epoch = sourceEpoch ?? _nextEpoch();
    if (epoch < _minimumSourceEpoch) return;
    try {
      final now = DateTime.now();
      final removed =
          rows.where((row) => row.id.isNotEmpty && !siriConversationIsIndexable(row, now)).map((row) => row.id).toSet();
      _fenceIneligible('conversation', removed, epoch);
      if (removed.isNotEmpty) await _removeRequired(uid, generation, 'conversation', removed);
      final projected = _conversationProjection(rows, epoch);
      await _nativeOperation(() async {
        if (_uid != uid || _accountGeneration != generation) return;
        if (projected.isNotEmpty) await _host.upsertConversations(uid, projected);
      }, indexWork: true);
    } catch (error) {
      Logger.debug('Siri conversation index failed: $error');
    }
  }

  /// The caller proves whether the server response is complete or covers a
  /// newest-page time window. An incremental mutation must use upsert instead.
  Future<void> reconcileConversations(List<ServerConversation> rows, {DateTime? coveredAfter, int? sourceEpoch}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    final epoch = sourceEpoch ?? _nextEpoch();
    if (epoch < _minimumSourceEpoch) return;
    _pendingReconciles['conversation'] = _PendingSiriReconcile('conversation', () async {
      if (_currentOwner(uid, generation) && epoch >= _minimumSourceEpoch) {
        await _host.reconcileConversations(
            uid, _conversationProjection(rows, epoch), coveredAfter?.millisecondsSinceEpoch);
      }
    });
    await _flushPendingWork(uid, generation);
  }

  List<SiriConversation> _conversationProjection(List<ServerConversation> rows, int sourceEpoch) {
    final now = DateTime.now();
    final newest = List<ServerConversation>.of(rows)
      ..sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    return newest
        .where((row) => siriConversationIsIndexable(row, now) && _allowsRow('conversation', row.id, sourceEpoch))
        .take(2000)
        .map(
          (row) => SiriConversation(
            id: row.id,
            title: row.structured.title,
            summary: row.structured.overview,
            startedAtMs: (row.startedAt ?? row.createdAt).millisecondsSinceEpoch,
            updatedAtMs: (row.finishedAt ?? row.createdAt).millisecondsSinceEpoch,
          ),
        )
        .toList();
  }

  Future<void> upsertMemories(List<Memory> rows, {int? sourceEpoch}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    final epoch = sourceEpoch ?? _nextEpoch();
    if (epoch < _minimumSourceEpoch) return;
    try {
      final now = DateTime.now();
      final removed = rows
          .where((row) => row.uid == uid && row.id.isNotEmpty && !siriMemoryIsIndexable(row, now, owner: uid))
          .map((row) => row.id)
          .toSet();
      _fenceIneligible('memory', removed, epoch);
      if (removed.isNotEmpty) await _removeRequired(uid, generation, 'memory', removed);
      final projected = _memoryProjection(rows, uid, epoch);
      await _nativeOperation(() async {
        if (_uid != uid || _accountGeneration != generation) return;
        if (projected.isNotEmpty) await _host.upsertMemories(uid, projected);
      }, indexWork: true);
    } catch (error) {
      Logger.debug('Siri memory index failed: $error');
    }
  }

  /// Only a complete, owner-wide and unfiltered traversal may call this.
  Future<void> reconcileMemories(List<Memory> rows, {int? sourceEpoch}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null || rows.any((row) => row.uid != uid)) return;
    final epoch = sourceEpoch ?? _nextEpoch();
    if (epoch < _minimumSourceEpoch) return;
    _pendingReconciles['memory'] = _PendingSiriReconcile('memory', () async {
      if (_currentOwner(uid, generation) && epoch >= _minimumSourceEpoch) {
        await _host.reconcileMemories(uid, _memoryProjection(rows, uid, epoch));
      }
    });
    await _flushPendingWork(uid, generation);
  }

  List<SiriMemory> _memoryProjection(List<Memory> rows, String uid, int sourceEpoch) {
    final now = DateTime.now();
    final newest = List<Memory>.of(rows)..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return newest
        .where((row) => siriMemoryIsIndexable(row, now, owner: uid) && _allowsRow('memory', row.id, sourceEpoch))
        .take(5000)
        .map(
          (row) => SiriMemory(
            id: row.id,
            content: row.content,
            createdAtMs: row.createdAt.millisecondsSinceEpoch,
            expiresAtMs: row.siriExpiryAt?.millisecondsSinceEpoch,
          ),
        )
        .toList();
  }

  /// The normal Memories view can be useful-now or device filtered. Read the
  /// owner-wide all view separately before removing any absent private item.
  /// A failed, truncated or capped traversal remains additive only.
  Future<void> refreshAuthoritativeMemories() async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    final sourceEpoch = _nextEpoch();
    const limit = 100;
    const maxPages = 50;
    final rows = <Memory>[];
    final seen = <String>{};
    var offset = 0;
    String? cursor;
    var complete = false;
    try {
      for (var page = 0; page < maxPages; page++) {
        final result =
            await (_testMemoryPageFetcher?.call(limit: limit, offset: cursor == null ? offset : 0, cursor: cursor) ??
                    getMemoriesResult(
                      limit: limit,
                      offset: cursor == null ? offset : 0,
                      cursor: cursor,
                      view: MemoryReadView.all,
                      forceView: true,
                    ))
                .timeout(const Duration(seconds: 10));
        if (_uid != uid || _accountGeneration != generation) return;
        if (!result.ok || result.truncated) break;
        rows.addAll(result.memories.where((row) => seen.add(row.id)));
        if (result.nextCursor != null) {
          if (result.nextCursor == cursor) break;
          cursor = result.nextCursor;
          continue;
        }
        if (cursor != null || result.memories.length < limit) {
          complete = true;
          break;
        }
        offset += result.memories.length;
      }
    } catch (error) {
      Logger.debug('Siri authoritative memory fetch failed: $error');
      return;
    }
    if (_uid != uid || _accountGeneration != generation) return;
    if (complete) {
      await _enqueueIndex((siri) => siri.reconcileMemories(rows, sourceEpoch: sourceEpoch));
    } else if (rows.isNotEmpty) {
      await _enqueueIndex((siri) => siri.upsertMemories(rows, sourceEpoch: sourceEpoch));
    }
  }

  Future<void> upsertTasks(List<ActionItemWithMetadata> rows, {int? sourceEpoch}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    final epoch = sourceEpoch ?? _nextEpoch();
    if (epoch < _minimumSourceEpoch) return;
    try {
      final now = DateTime.now();
      final removed =
          rows.where((row) => row.id.isNotEmpty && !siriTaskIsIndexable(row, now)).map((row) => row.id).toSet();
      _fenceIneligible('task', removed, epoch);
      if (removed.isNotEmpty) await _removeRequired(uid, generation, 'task', removed);
      final projected = _taskProjection(rows, epoch);
      await _nativeOperation(() async {
        if (_uid != uid || _accountGeneration != generation) return;
        if (projected.isNotEmpty) await _host.upsertTasks(uid, projected);
      }, indexWork: true);
    } catch (error) {
      Logger.debug('Siri task index failed: $error');
    }
  }

  /// Only a completed unfiltered task traversal may call this. An active-only
  /// result cannot remove recent completed tasks from the native snapshot.
  Future<void> reconcileTasks(List<ActionItemWithMetadata> rows,
      {required bool includeCompleted, int? sourceEpoch}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    final epoch = sourceEpoch ?? _nextEpoch();
    if (epoch < _minimumSourceEpoch) return;
    _pendingReconciles['task'] = _PendingSiriReconcile('task', () async {
      if (_currentOwner(uid, generation) && epoch >= _minimumSourceEpoch) {
        await _host.reconcileTasks(uid, _taskProjection(rows, epoch), includeCompleted);
      }
    });
    await _flushPendingWork(uid, generation);
  }

  List<SiriTask> _taskProjection(List<ActionItemWithMetadata> rows, int sourceEpoch) {
    final now = DateTime.now();
    return rows
        .where((row) => siriTaskIsIndexable(row, now) && _allowsRow('task', row.id, sourceEpoch))
        .map(
          (row) => SiriTask(
            id: row.id,
            title: row.description,
            completed: row.completed,
            createdAtMs: (row.createdAt ?? DateTime.now()).millisecondsSinceEpoch,
            dueAtMs: row.dueAt?.millisecondsSinceEpoch,
            completedAtMs: row.completedAt?.millisecondsSinceEpoch,
          ),
        )
        .toList();
  }

  Future<void> delete(String type, String id) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null) return;
    await _removeRequired(uid, generation, type, [id]);
  }

  Future<void> deleteMany(String type, List<String> ids, {String? expectedUid}) async {
    final uid = _uid;
    final generation = _accountGeneration;
    if (!_isIOS || uid == null || ids.isEmpty || (expectedUid != null && uid != expectedUid)) return;
    await _removeRequired(uid, generation, type, ids);
  }

  Future<bool> isEnabled() async {
    if (!_isIOS) return false;
    // This reads only a persisted preference. Do not queue it behind indexing.
    return _host.isEnabled().timeout(_nativeTimeout);
  }

  Future<void> setEnabled(bool enabled) async {
    if (!_isIOS) return;
    await _nativeOperation(() => _host.setEnabled(enabled));
    if (enabled && _uid != null) {
      _ownerWideRefreshAt = null;
      _scheduleOwnerWideRefresh(_uid!, _accountGeneration);
    }
  }

  Future<String?> takePendingRoute() async => _isIOS ? _host.takePendingRoute() : null;

  @override
  void memoryCreated(String id) {
    final context = globalNavigatorKey.currentContext;
    if (context != null) unawaited(context.read<MemoriesProvider>().loadMemories());
  }

  @override
  void taskChanged(String id) {
    final context = globalNavigatorKey.currentContext;
    if (context != null) unawaited(context.read<ActionItemsProvider>().fetchActionItems());
  }

  @override
  Future<bool> openRoute(String route) => HomeNavigation.openRoute(route);

  @override
  Future<void> setListening(bool enabled) async {
    final capture = _testListeningCapture ??
        (() {
          final context = globalNavigatorKey.currentContext;
          if (context == null) throw StateError('Omi is not ready');
          final provider = context.read<CaptureProvider>();
          final device = context.read<DeviceProvider>();
          return (
            start: () async {
              await provider.streamRecording();
            },
            stop: () => provider.stopStreamRecording(),
            source: () => provider.liveCaptureSource,
            deviceConnected: () => device.isConnected,
            phoneBatchRecording: () => provider.isPhoneMicBatchRecording,
            deviceBatchRecording: () => provider.isPendantBatchRecording,
            phonePaused: () =>
                provider.isPhoneMicPaused || (provider.liveCaptureSource == 'phone' && provider.isPaused),
          );
        })();
    if (enabled) {
      if (capture.deviceConnected() &&
          (capture.deviceBatchRecording() || (capture.source() != null && capture.source() != 'phone'))) {
        throw PlatformException(
          code: 'device_already_listening',
          message: 'Omi is already listening from your device.',
        );
      }
      if ((capture.source() == 'phone' || capture.phoneBatchRecording()) && capture.phonePaused()) {
        throw PlatformException(code: 'capture_paused', message: 'Omi is paused. Open Omi to resume.');
      }
      if (capture.source() == 'phone' || capture.phoneBatchRecording()) return;
      try {
        await capture.start();
      } catch (_) {
        if (_testListeningCapture == null) {
          final status = await Permission.microphone.status;
          if (status.isDenied || status.isPermanentlyDenied || status.isRestricted) {
            throw PlatformException(code: 'mic_permission_denied', message: 'Allow microphone access in Omi first.');
          }
        }
        rethrow;
      }
    } else {
      if (capture.source() != 'phone' && !capture.phoneBatchRecording()) {
        throw PlatformException(code: 'nothing_to_stop', message: "Omi isn't listening right now.");
      }
      if (!await capture.stop()) throw StateError('Phone conversation capture did not stop');
    }
  }

  Future<void> setCurrentScreen(String route, String? id) async {
    if (_isIOS) await _host.setCurrentScreen(route, id);
  }

  Future<void> donateUiAction(String type, String id) async {
    final uid = _uid;
    if (!_isIOS || uid == null || id.isEmpty) return;
    try {
      await _host.donateAction(uid, type, id);
    } catch (error) {
      Logger.debug('Siri donation failed: $error');
    }
  }

  Future<void> _flushTelemetry() async {
    final rows = await _host.takeTelemetry();
    for (final row in rows) {
      if (row.kind == 'intent') {
        if (row.intent == 'askOmi') {
          final outcomes = siri_events.SiriAskOmiPerformedOutcome.values.where((value) => value.name == row.outcome);
          const TypedEvents().emit(siri_events.SiriAskOmiPerformed(
            platform: siri_events.SiriAskOmiPerformedPlatform.ios,
            outcome: outcomes.isEmpty ? siri_events.SiriAskOmiPerformedOutcome.server : outcomes.first,
            latencyMs: row.latencyMs,
            invokedVia: siri_events.SiriAskOmiPerformedInvokedVia.unknown,
          ));
          continue;
        }
        final intents = siri_events.SiriIntentPerformedIntent.values.where((value) => value.name == row.intent);
        if (intents.isEmpty) continue;
        final outcomes = siri_events.SiriIntentPerformedOutcome.values.where((value) => value.name == row.outcome);
        const TypedEvents().emit(
          siri_events.SiriIntentPerformed(
            intent: intents.first,
            platform: siri_events.SiriIntentPerformedPlatform.ios,
            outcome: outcomes.isEmpty ? siri_events.SiriIntentPerformedOutcome.server : outcomes.first,
            latencyMs: row.latencyMs,
            invokedVia: siri_events.SiriIntentPerformedInvokedVia.unknown,
          ),
        );
      } else if (row.kind == 'index') {
        final outcomes = siri_events.SiriIndexRebuiltOutcome.values.where((value) => value.name == row.outcome);
        const TypedEvents().emit(
          siri_events.SiriIndexRebuilt(
            platform: siri_events.SiriIndexRebuiltPlatform.ios,
            entityCounts: row.entityCounts,
            durationMs: row.latencyMs,
            outcome: outcomes.isEmpty ? siri_events.SiriIndexRebuiltOutcome.server : outcomes.first,
          ),
        );
      }
    }
  }
}
