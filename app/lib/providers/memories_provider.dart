import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/services/client_device_service.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/extensions/string.dart';

typedef FetchMemoriesRequest = Future<GetMemoriesResult> Function({
  int limit,
  int offset,
  bool thisDeviceOnly,
});
typedef FetchMemoriesCursorRequest = Future<GetMemoriesResult> Function({
  int limit,
  int offset,
  bool thisDeviceOnly,
  String? cursor,
  MemoryReadView? view,
});
typedef FetchLedgerHistoryRequest = Future<GetLedgerHistoryResult> Function({int limit, int offset});
typedef FetchLedgerHistoryCursorRequest = Future<GetLedgerHistoryResult> Function({
  int limit,
  int offset,
  String? cursor,
});
typedef ReviewMemoryRequest = Future<bool> Function(String memoryId, bool value);
typedef EditMemoryRequest = Future<EditMemoryResult> Function(String memoryId, String value);
typedef RevertMemoryRequest = Future<RevertMemoryResult> Function(String memoryId, String operationId);
typedef MemoryUseRequest = Future<MemoryUseResult> Function({
  required String memoryId,
  required MemoryUseAction action,
  required String feedbackId,
});

/// The default memory collection is useful-now. History is an explicit owner
/// action and remains available without changing the underlying records.
enum MemoryCollectionView { usefulNow, history, all }

MemoryReadView _serverViewForCollection(MemoryCollectionView view) {
  switch (view) {
    case MemoryCollectionView.usefulNow:
      return MemoryReadView.usefulNow;
    case MemoryCollectionView.history:
      return MemoryReadView.history;
    case MemoryCollectionView.all:
      return MemoryReadView.all;
  }
}

Future<GetLedgerHistoryResult> _noLedgerHistory({
  int limit = 500,
  int offset = 0,
}) async =>
    const GetLedgerHistoryResult([], supported: false);

Future<GetMemoriesResult> _getMemoriesCursorPage({
  int limit = 100,
  int offset = 0,
  bool thisDeviceOnly = false,
  String? cursor,
  MemoryReadView? view,
}) =>
    getMemoriesResult(
      limit: limit,
      offset: offset,
      thisDeviceOnly: thisDeviceOnly,
      cursor: cursor,
      view: view,
      forceView: view != null,
    );

class MemoriesProvider extends ChangeNotifier {
  List<Memory> _memories = [];
  bool _loading = true;
  String _searchQuery = '';
  Set<MemoryCategory> _selectedCategories = {};
  bool _showOnlyManual = false;
  bool _filterThisDeviceOnly = false;
  bool _deviceScopeSupported = true;
  bool _ledgerHistorySupported = false;
  bool _ledgerHistoryTruncated = false;
  bool _ledgerHistoryHasMore = false;
  int _ledgerHistoryOffset = 0;
  String? _ledgerHistoryNextCursor;
  bool? _beliefEnabled = memoryBeliefCapability;
  MemoryCollectionView _collectionView = MemoryCollectionView.usefulNow;
  bool _loadFailed = false;
  bool _hasLoaded = false;
  Future<void>? _clientDeviceInitialization;
  List<Tuple2<MemoryCategory, int>> categories = [];
  MemoryCategory? selectedCategory;

  // Connectivity handling for offline sync
  ConnectivityProvider? _connectivityProvider;
  bool _isSyncing = false;
  int _sessionGeneration = 0;
  int _loadSequence = 0;
  int _ledgerProjectionRevision = 0;
  final FetchMemoriesRequest _fetchMemoriesRequest;
  final FetchMemoriesCursorRequest? _fetchMemoriesCursorRequest;
  final FetchLedgerHistoryRequest _fetchLedgerHistoryRequest;
  final FetchLedgerHistoryCursorRequest? _fetchLedgerHistoryCursorRequest;
  final Future<bool> Function(String) _deleteMemoryRequest;
  final ReviewMemoryRequest _reviewMemoryRequest;
  final EditMemoryRequest _editMemoryRequest;
  final RevertMemoryRequest _revertMemoryRequest;
  final MemoryUseRequest _memoryUseRequest;
  final Set<String> _revertingMemoryIds = {};
  final Map<String, String> _revertOperationIds = {};
  final Set<String> _memoryUseInFlight = {};
  final Map<String, String> _memoryUseFeedbackIds = {};

  /// Verdicts persisted this session for ids the loaded list does not resolve
  /// (cold provider, truncated bulk list, or rows GET /v3/memories filters
  /// out). A live row always wins; this only keeps recap rows honest while
  /// nothing answers for the id.
  final Map<String, bool> _settledUnresolvedReviews = {};

  /// Hydration asks review cards have made, per id. Instance state so a card
  /// State rebuilt by scrolling does not re-count, and `clearUserData()` can
  /// reset the budget when the account changes.
  final Map<String, int> _externalHydrateAttempts = {};
  static const int _maxExternalHydrateAttempts = 2;

  /// The load currently in flight, with the parameters it was started with.
  /// Concurrent same-parameter callers join it instead of starting races the
  /// sequence guard would discard.
  Future<void>? _inFlightLoad;
  int _inFlightLoadLimit = 100;
  bool _inFlightLoadDeviceScoped = false;
  MemoryCollectionView _inFlightLoadView = MemoryCollectionView.usefulNow;

  /// True while a history continuation is in flight. A second concurrent
  /// load-more must not read the same offset page and advance the offset
  /// again; it returns and the next tap continues from the completed page.
  bool _loadingMoreHistory = false;

  MemoriesProvider({
    FetchMemoriesRequest? fetchMemoriesRequest,
    FetchMemoriesCursorRequest? fetchMemoriesCursorRequest,
    FetchLedgerHistoryRequest? fetchLedgerHistoryRequest,
    FetchLedgerHistoryCursorRequest? fetchLedgerHistoryCursorRequest,
    Future<bool> Function(String)? deleteMemoryRequest,
    ReviewMemoryRequest? reviewMemoryRequest,
    EditMemoryRequest? editMemoryRequest,
    RevertMemoryRequest? revertMemoryRequest,
    MemoryUseRequest? memoryUseRequest,
  })  : _fetchMemoriesRequest = fetchMemoriesRequest ?? getMemoriesResult,
        _fetchMemoriesCursorRequest =
            fetchMemoriesCursorRequest ?? (fetchMemoriesRequest == null ? _getMemoriesCursorPage : null),
        _fetchLedgerHistoryRequest =
            fetchLedgerHistoryRequest ?? (fetchMemoriesRequest == null ? getLedgerHistory : _noLedgerHistory),
        _fetchLedgerHistoryCursorRequest = fetchLedgerHistoryCursorRequest ??
            (fetchMemoriesRequest == null && fetchLedgerHistoryRequest == null ? getLedgerHistory : null),
        _deleteMemoryRequest = deleteMemoryRequest ?? deleteMemoryServer,
        _reviewMemoryRequest = reviewMemoryRequest ?? reviewMemoryServer,
        _editMemoryRequest = editMemoryRequest ?? editMemoryServer,
        _revertMemoryRequest = revertMemoryRequest ?? revertMemoryServer,
        _memoryUseRequest = memoryUseRequest ?? useMemoryServer;

  List<Memory> get memories => _memories;
  bool get loading => _loading;
  String get searchQuery => _searchQuery;
  Set<MemoryCategory> get selectedCategories => _selectedCategories;
  bool get showOnlyManual => _showOnlyManual;
  bool get filterThisDeviceOnly => _filterThisDeviceOnly;
  bool get hasPendingMemories => SharedPreferencesUtil().pendingMemories.isNotEmpty;
  int get pendingMemoriesCount => SharedPreferencesUtil().pendingMemories.length;
  bool get ledgerHistorySupported => _ledgerHistorySupported;
  bool get ledgerHistoryTruncated => _ledgerHistoryTruncated;
  bool get ledgerHistoryHasMore => _ledgerHistoryHasMore;
  String? get ledgerHistoryNextCursor => _ledgerHistoryNextCursor;
  bool get memoryBeliefEnabled => _beliefEnabled == true;
  MemoryCollectionView get collectionView => _collectionView;
  bool get showHistory => _collectionView == MemoryCollectionView.history;
  bool get showAll => _collectionView == MemoryCollectionView.all;
  bool get loadFailed => _loadFailed;

  /// Whether a load attempt has already completed in this session (success or
  /// failure). `_loading` starts `true` before anything was ever fetched, so
  /// callers that need "a fetch is actually in flight" must check
  /// `loading && hasLoaded`.
  bool get hasLoaded => _hasLoaded;
  bool get showLoadError => _loadFailed && _memories.isEmpty;

  /// The verdict this session persisted for [memoryId] when no live row
  /// resolves the id, or null when no verdict has been recorded. A live row's
  /// `userReview` always wins over this.
  bool? settledReviewFor(String memoryId) => _settledUnresolvedReviews[memoryId];

  /// Consume one hydration ask for [memoryId]: true while the id is still
  /// eligible (first ask free, then retries only while loads keep failing).
  /// Instance-scoped so `clearUserData()` restores eligibility for a new
  /// account session.
  bool consumeHydrationAsk(String memoryId) {
    final attempts = _externalHydrateAttempts[memoryId] ?? 0;
    final allowed = attempts == 0 || (attempts < _maxExternalHydrateAttempts && _loadFailed);
    if (allowed) {
      _externalHydrateAttempts[memoryId] = attempts + 1;
    }
    return allowed;
  }

  bool isRevertingMemory(String memoryId) => _revertingMemoryIds.contains(memoryId);

  bool isApplyingMemoryUse(String memoryId) => _memoryUseInFlight.contains(memoryId);

  bool canRevertSupersededFact(Memory memory) {
    if (!_isEligibleSupersededFact(memory)) return false;
    final alreadyRestored = _memories.any(
      (candidate) =>
          candidate.isCurrentKnowledgeLedgerRow &&
          candidate.evidence.any(
            (evidence) => evidence['source_type'] == 'explicit_user_revert' && evidence['source_id'] == memory.id,
          ),
    );
    if (alreadyRestored) return false;
    final currentTail = _matchingCurrentTail(memory);
    return currentTail == null || currentTail.content.trim() != memory.content.trim();
  }

  static bool _isEligibleSupersededFact(Memory memory) {
    return memory.ledgerSchemaVersion == 'knowledge_ledger.v1' &&
        memory.ledgerKind == KnowledgeLedgerKind.fact &&
        memory.intentBacked &&
        !memory.deleted &&
        !memory.isLocked &&
        memory.userReview != false &&
        memory.invalidAt != null &&
        (memory.supersededBy ?? '').trim().isNotEmpty;
  }

  List<Memory> get currentLedgerFacts => _memories
      .where(
        (memory) => memory.isCurrentKnowledgeLedgerRow && memory.ledgerKind == KnowledgeLedgerKind.fact,
      )
      .toList(growable: false)
    ..sort(_ledgerOrder);

  List<Memory> get currentLedgerPlaybooks => _memories
      .where(
        (memory) => memory.isCurrentKnowledgeLedgerRow && memory.isLedgerPlaybook,
      )
      .toList(growable: false)
    ..sort(_ledgerOrder);

  List<Memory> get currentLedgerTriggers => _memories
      .where(
        (memory) => memory.isCurrentKnowledgeLedgerRow && memory.isLedgerTrigger,
      )
      .toList(growable: false)
    ..sort(_ledgerOrder);

  List<Memory> get historicalLedgerRows =>
      _memories.where((memory) => memory.isHistoricalKnowledgeLedgerRow).toList(growable: false)
        ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));

  static int _ledgerOrder(Memory a, Memory b) {
    final weight = b.curationWeight.compareTo(a.curationWeight);
    if (weight != 0) return weight;
    final slot = (a.ledgerSlot ?? '').compareTo(b.ledgerSlot ?? '');
    if (slot != 0) return slot;
    // Match the canonical backend/macOS renderer exactly. Recency authority
    // between concurrently open same-slot rows remains a ratification gate;
    // clients must not silently invent a different winner meanwhile.
    final validAt = (a.validAt ?? a.updatedAt).compareTo(
      b.validAt ?? b.updatedAt,
    );
    if (validAt != 0) return validAt;
    return a.id.compareTo(b.id);
  }

  List<Memory> get filteredMemories {
    return _memories.where((memory) {
      // Historical rows remain in the provider so review/revert and an
      // explicit history view can use the authoritative record. The default
      // list keeps them out of the useful-now experience.
      // A missing/false capability means the server returned the legacy
      // combined projection; preserve every row until a true header opts this
      // client into temporal filtering.
      final temporalMatch = _beliefEnabled != true ||
          switch (_collectionView) {
            MemoryCollectionView.usefulNow => memory.isUsefulNow && memory.memoryUseSuppressed != true,
            // The server owns the history/all projection. Keep these rows
            // visible locally so retained dated and suppressed rows returned
            // by the requested view are not filtered back out.
            MemoryCollectionView.history || MemoryCollectionView.all => true,
          };

      // Apply search filter
      final matchesSearch = _searchQuery.isEmpty ||
          memory.content.decodeString.toLowerCase().contains(
                _searchQuery.toLowerCase(),
              );

      // Apply category filter or exclusion logic
      bool categoryMatch;
      if (_showOnlyManual) {
        // Show only manual memories (exclude system and interesting)
        categoryMatch = memory.category == MemoryCategory.manual;
      } else if (_selectedCategories.isNotEmpty) {
        // Show only selected categories
        categoryMatch = _selectedCategories.contains(memory.category);
      } else {
        // Show all categories if no filter is applied
        categoryMatch = true;
      }

      // When the server does not support device_scope, legacy memories have no
      // primary_capture_device/capture_device_ids. Skip the local device filter
      // in that case to avoid hiding all legacy rows on the "This device" view.
      final deviceMatch = !_filterThisDeviceOnly ||
          !_deviceScopeSupported ||
          ClientDeviceService.instance.memoryMatchesThisDevice(
            primaryCaptureDevice: memory.primaryCaptureDevice,
            captureDeviceIds: memory.captureDeviceIds,
          );

      return temporalMatch && matchesSearch && categoryMatch && deviceMatch;
    }).toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  void setCollectionView(MemoryCollectionView view) {
    if (_collectionView == view) return;
    _collectionView = view;
    notifyListeners();
    // Each server view owns a different cursor stream. Start a new bounded
    // traversal rather than applying a local filter to the previous view.
    unawaited(loadMemories());
  }

  Future<GetMemoriesResult> _fetchMemoryPage({
    required int limit,
    required int offset,
    required bool thisDeviceOnly,
    String? cursor,
    MemoryReadView? view,
  }) {
    final cursorRequest = _fetchMemoriesCursorRequest;
    if (cursorRequest != null) {
      return cursorRequest(
        limit: limit,
        offset: offset,
        thisDeviceOnly: thisDeviceOnly,
        cursor: cursor,
        view: view,
      );
    }
    // A caller-provided legacy fetcher has no cursor contract. The load loop
    // stops before reaching this branch with a non-null cursor, so this is only
    // used for the initial offset page.
    return _fetchMemoriesRequest(
      limit: limit,
      offset: offset,
      thisDeviceOnly: thisDeviceOnly,
    );
  }

  Future<GetLedgerHistoryResult> _fetchHistoryPage({
    required int limit,
    required int offset,
    String? cursor,
  }) {
    final cursorRequest = _fetchLedgerHistoryCursorRequest;
    if (cursorRequest != null) {
      return cursorRequest(limit: limit, offset: offset, cursor: cursor);
    }
    return _fetchLedgerHistoryRequest(limit: limit, offset: offset);
  }

  void setFilterThisDeviceOnly(bool enabled) {
    _filterThisDeviceOnly = enabled;
    notifyListeners();
    loadMemories();
  }

  Future<void> _ensureClientDeviceInitialized() {
    if (ClientDeviceService.instance.deviceIdHash.isNotEmpty) {
      return Future.value();
    }
    _clientDeviceInitialization ??= ClientDeviceService.instance.initialize();
    return _clientDeviceInitialization!;
  }

  void setShowOnlyManual(bool showOnly) {
    _showOnlyManual = showOnly;
    notifyListeners();
  }

  void setCategory(MemoryCategory? category) {
    selectedCategory = category;
    notifyListeners();
  }

  void setSearchQuery(String query) {
    _searchQuery = query.toLowerCase();
    notifyListeners();
  }

  void toggleCategoryFilter(MemoryCategory category) async {
    if (_selectedCategories.contains(category)) {
      _selectedCategories.remove(category);
    } else {
      _selectedCategories.add(category);
    }
    _showOnlyManual = false; // Reset manual-only filter when setting a category filter
    notifyListeners();

    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      'memories_filter_categories',
      _selectedCategories.map((e) => e.name).toList(),
    );
  }

  void clearCategoryFilter() async {
    _selectedCategories.clear();
    _showOnlyManual = false;
    notifyListeners();

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('memories_filter_categories');
    // Clear old single filter key as well to be clean
    await prefs.remove('memories_filter');
  }

  void clearUserData() {
    _sessionGeneration++;
    _memories = [];
    _selectedCategories = {};
    _showOnlyManual = false;
    _searchQuery = '';
    _filterThisDeviceOnly = false;
    _ledgerHistorySupported = false;
    _ledgerHistoryTruncated = false;
    _ledgerHistoryHasMore = false;
    _ledgerHistoryOffset = 0;
    _ledgerHistoryNextCursor = null;
    _beliefEnabled = null;
    _collectionView = MemoryCollectionView.usefulNow;
    categories = [];
    selectedCategory = null;
    _loading = false;
    _hasLoaded = false;
    _loadFailed = false;
    _isSyncing = false;
    _revertingMemoryIds.clear();
    _revertOperationIds.clear();
    _memoryUseInFlight.clear();
    _memoryUseFeedbackIds.clear();
    _settledUnresolvedReviews.clear();
    _externalHydrateAttempts.clear();
    _cancelDeletionTimer();
    _lastDeletedMemory = null;
    _pendingDeletionId = null;
    notifyListeners();
  }

  // Deprecated/Modified: kept as alias if needed but unused internally now
  void setCategoryFilter(MemoryCategory? category) {
    // Do nothing or migrate logic if called from legacy code?
    // Assuming we are updating all call sites.
  }

  void _setCategories() {
    categories = MemoryCategory.values.map((category) {
      final count = memories.where((memory) => memory.category == category).length;
      return Tuple2(category, count);
    }).toList();
    notifyListeners();
  }

  Future<void> init() async {
    final generation = _sessionGeneration;
    // Device-id hydration and saved-filter loading are best-effort. A failure
    // here (secure storage / SharedPreferences hiccup) must NOT abort init
    // before loadMemories() runs, or _loading stays at its constructor default
    // `true` and the screen is stuck on the loading skeleton forever.
    try {
      await _ensureClientDeviceInitialized();
    } catch (e) {
      Logger.error(
        'MemoriesProvider: client-device init failed (non-fatal): $e',
      );
    }
    if (generation != _sessionGeneration) return;
    try {
      await _loadFilter();
    } catch (e) {
      Logger.error('MemoriesProvider: filter load failed (non-fatal): $e');
    }
    if (generation != _sessionGeneration) return;
    await loadMemories();
    if (generation != _sessionGeneration) return;
    // Try to sync any pending memories on init
    await syncPendingMemories();
  }

  /// Set the connectivity provider to listen for connection changes
  void setConnectivityProvider(ConnectivityProvider provider) {
    if (identical(_connectivityProvider, provider)) return;
    _connectivityProvider?.removeListener(_onConnectivityChanged);
    _connectivityProvider = provider;
    _connectivityProvider?.addListener(_onConnectivityChanged);
  }

  void _onConnectivityChanged() {
    if (_connectivityProvider?.isConnected == true) {
      // Connection restored, try to sync pending memories
      syncPendingMemories();
    }
  }

  @override
  void dispose() {
    _connectivityProvider?.removeListener(_onConnectivityChanged);
    super.dispose();
  }

  Future<void> _loadFilter() async {
    final prefs = await SharedPreferences.getInstance();

    final filterList = prefs.getStringList('memories_filter_categories');

    if (filterList == null) {
      _selectedCategories = {
        MemoryCategory.system,
        MemoryCategory.interesting,
        MemoryCategory.manual,
        MemoryCategory.workflow,
      };
    } else {
      _selectedCategories = filterList
          .map(
            (e) => MemoryCategory.values.firstWhere(
              (c) => c.name == e,
              orElse: () => MemoryCategory.system,
            ),
          )
          .toSet();
    }
    notifyListeners();
  }

  Future<void> loadMemories({int limit = 100}) async {
    // Coalesce concurrent callers: several review cards can mount while the
    // first fetch is still in flight (before `hasLoaded` flips), and racing
    // loads would be discarded one after another by the sequence guard. A
    // caller with different parameters gets its own load, which supersedes the
    // in-flight one via the sequence guard as before.
    final inFlight = _inFlightLoad;
    if (inFlight != null &&
        _inFlightLoadLimit == limit &&
        _inFlightLoadDeviceScoped == _filterThisDeviceOnly &&
        _inFlightLoadView == _collectionView) {
      try {
        await inFlight;
      } catch (_) {}
      return;
    }
    await _startMemoryLoad(limit: limit);
  }

  /// Start a new read even when an older request is still in flight. This is
  /// reserved for mutations whose confirmation must come from a post-action
  /// server projection rather than a request that started before the action.
  Future<void> _loadMemoriesFresh({int limit = 100}) {
    return _startMemoryLoad(limit: limit);
  }

  Future<void> _startMemoryLoad({required int limit}) async {
    final loadFuture = _loadMemoriesInternal(limit: limit);
    _inFlightLoad = loadFuture;
    _inFlightLoadLimit = limit;
    _inFlightLoadDeviceScoped = _filterThisDeviceOnly;
    _inFlightLoadView = _collectionView;
    try {
      await loadFuture;
    } finally {
      if (identical(_inFlightLoad, loadFuture)) {
        _inFlightLoad = null;
      }
    }
  }

  Future<void> _loadMemoriesInternal({int limit = 100}) async {
    final generation = _sessionGeneration;
    final loadSequence = ++_loadSequence;
    _beliefEnabled ??= memoryBeliefCapability;
    final serverView = _serverViewForCollection(_collectionView);
    final ledgerProjectionRevision = _ledgerProjectionRevision;
    // Snapshot the pending-deletion ID before any await: a refresh that
    // started during the undo window must still suppress the deleted item
    // even if _finalizeDeletion() clears the field while the fetch is in
    // flight.
    final tombstoneId = _pendingDeletionId;
    _loading = true;
    notifyListeners();

    if (_filterThisDeviceOnly) {
      // Best-effort: if device-id hydration fails, fall through and load all
      // memories (local device filtering is skipped) rather than leaving
      // _loading stuck true, which was set just above.
      try {
        await _ensureClientDeviceInitialized();
      } catch (e) {
        Logger.error(
          'MemoriesProvider: device init during load failed (non-fatal): $e',
        );
      }
      if (generation != _sessionGeneration || loadSequence != _loadSequence) {
        return;
      }
    }

    // Page until a short page: backend no longer expands the first page to 5000
    // (prod GET /v3/memories 504s). Cap total fetch so a huge account cannot hang the UI.
    const maxPages = 20;
    final all = <Memory>[];
    final seenCurrent = <String>{};
    var offset = 0;
    String? memoryCursor;
    var viewProtocolRestarts = 0;
    var deviceScopeSupported = true;
    var ledgerHistorySupported = false;
    var ledgerHistoryTruncated = false;
    var ledgerHistoryHasMore = false;
    var ledgerHistoryOffset = 0;
    String? ledgerHistoryNextCursor;
    for (var page = 0; page < maxPages; page++) {
      final result = await _fetchMemoryPage(
        limit: limit,
        // Cursor pages and offset pages are different protocols. The API
        // rejects a non-zero offset with a cursor, so reset the offset when a
        // server continuation marker takes over.
        offset: memoryCursor == null ? offset : 0,
        thisDeviceOnly: _filterThisDeviceOnly,
        cursor: memoryCursor,
        // Do not send a temporal selector until the capability probe has
        // confirmed it. A restart below binds the first cursor page to the
        // same selector used by every continuation page.
        view: _beliefEnabled == true ? serverView : null,
      );
      if (generation != _sessionGeneration || loadSequence != _loadSequence) {
        return;
      }
      if (!result.ok) {
        _loadFailed = true;
        final cached = SharedPreferencesUtil().cachedMemories;
        if (cached.isNotEmpty) {
          _memories = cached;
          _setCategories();
        }
        _loading = false;
        _hasLoaded = true;
        notifyListeners();
        return;
      }
      deviceScopeSupported = result.deviceScopeSupported;
      final requestedView = _beliefEnabled == true ? serverView : null;
      // A missing header is a capability reset. Do not let a prior true value
      // leak into a stable/older response on the next page or account.
      _beliefEnabled = result.beliefEnabled;
      final responseUsesTemporalView = result.beliefEnabled == true;
      if ((requestedView != null) != responseUsesTemporalView) {
        if (viewProtocolRestarts < 2) {
          viewProtocolRestarts++;
          all.clear();
          seenCurrent.clear();
          offset = 0;
          memoryCursor = null;
          Logger.debug(
            'MemoriesProvider: restarting memory read after capability/view change',
          );
          continue;
        }
        Logger.warning(
          'MemoriesProvider: capability/view changed repeatedly; stopping before mixing cursor protocols',
        );
        break;
      }
      all.addAll(result.memories.where((memory) => seenCurrent.add(memory.id)));
      // A truncated page is an honest partial response with no resumable cursor;
      // stop loading instead of continuing with an unstable offset.
      if (result.truncated) {
        if (result.truncated) {
          Logger.warning(
            'MemoriesProvider: server returned a truncated list; stopping at ${seenCurrent.length} rows',
          );
        }
        break;
      }
      if (result.nextCursor != null) {
        if (_fetchMemoriesCursorRequest == null) {
          // A legacy injected fetcher cannot honor the server cursor. Do not
          // fall back to an offset after a cursor page; that would duplicate
          // or skip rows and falsely report a complete projection.
          Logger.warning(
            'MemoriesProvider: server returned a cursor without a cursor fetcher',
          );
          break;
        }
        if (result.nextCursor == memoryCursor) {
          Logger.warning(
            'MemoriesProvider: server repeated the same memory cursor; stopping',
          );
          break;
        }
        memoryCursor = result.nextCursor;
        continue;
      }
      if (result.memories.length < limit) break;
      offset += result.memories.length;
    }
    // History is an additive owner-scoped projection, fetched independently
    // from the current list because GET /v3/memories intentionally filters
    // rejected and closed rows. Device-scoped history has no ratified server
    // contract, so the "This device" view remains current-only.
    if (!_filterThisDeviceOnly) {
      final seen = all.map((memory) => memory.id).toSet();
      const historyPageSize = 500;
      const maxHistoryPages = 10;
      var historyOffset = 0;
      var historyRowsLoaded = 0;
      String? historyCursor;
      for (var page = 0; page < maxHistoryPages; page++) {
        final result = await _fetchHistoryPage(
          limit: historyPageSize,
          offset: historyOffset,
          cursor: historyCursor,
        );
        if (generation != _sessionGeneration || loadSequence != _loadSequence) {
          return;
        }
        ledgerHistorySupported = result.supported;
        // Every history response is authoritative for the beta capability.
        // Missing/false headers reset useful-now filtering to stable behavior.
        _beliefEnabled = result.beliefEnabled;
        if (!result.supported) break;
        all.addAll(result.memories.where((memory) => seen.add(memory.id)));
        historyRowsLoaded += result.memories.length;
        ledgerHistoryOffset += result.memories.length;
        ledgerHistoryNextCursor = result.nextCursor;
        if (result.nextCursor != null) {
          if (_fetchLedgerHistoryCursorRequest == null) {
            Logger.warning(
              'MemoriesProvider: ledger history returned a cursor without a cursor fetcher',
            );
            ledgerHistoryTruncated = true;
            ledgerHistoryHasMore = true;
            break;
          }
          historyCursor = result.nextCursor;
          ledgerHistoryTruncated = true;
          ledgerHistoryHasMore = true;
          continue;
        }
        if (result.truncated) {
          ledgerHistoryTruncated = true;
          ledgerHistoryHasMore = true;
          break;
        }
        // Once a cursor stream has started, switching back to offset paging
        // would duplicate or skip rows. A cursor page without a continuation
        // is complete even when it is shorter than the requested limit.
        if (historyCursor != null) {
          ledgerHistoryTruncated = false;
          ledgerHistoryHasMore = false;
          break;
        }
        if (result.memories.length < historyPageSize) break;
        historyOffset += result.memories.length;
        if (page == maxHistoryPages - 1) ledgerHistoryTruncated = true;
        if (page == maxHistoryPages - 1) ledgerHistoryHasMore = true;
      }
      if (ledgerHistoryTruncated) {
        Logger.warning(
          'MemoriesProvider: ledger history is partial; loaded $historyRowsLoaded rows',
        );
      }
    }
    if (generation != _sessionGeneration ||
        loadSequence != _loadSequence ||
        ledgerProjectionRevision != _ledgerProjectionRevision) {
      if (generation == _sessionGeneration && loadSequence == _loadSequence) {
        _loading = false;
        _hasLoaded = true;
        notifyListeners();
      }
      return;
    }
    // Keep an optimistic delete hidden throughout its undo window. Use the
    // snapshot taken before the fetch so a concurrent finalization that
    // clears _pendingDeletionId mid-fetch cannot reinsert the row.
    // Re-check _pendingDeletionId at apply time: if the user deleted a memory
    // after loadMemories() started (tombstoneId was null at snapshot), the
    // stale response still contains it and would reinsert the row.
    final currentTombstoneId = _pendingDeletionId;
    final effectiveTombstoneId = currentTombstoneId ?? tombstoneId;
    _memories = effectiveTombstoneId != null ? all.where((memory) => memory.id != effectiveTombstoneId).toList() : all;
    _deviceScopeSupported = deviceScopeSupported;
    _ledgerHistorySupported = ledgerHistorySupported;
    _ledgerHistoryTruncated = ledgerHistoryTruncated;
    _ledgerHistoryHasMore = ledgerHistoryHasMore;
    _ledgerHistoryOffset = ledgerHistoryOffset;
    _ledgerHistoryNextCursor = ledgerHistoryNextCursor;
    _loadFailed = false;

    // Merge pending memories that haven't synced yet
    final pendingMemories = SharedPreferencesUtil().pendingMemories;
    for (var pending in pendingMemories) {
      if (pending.id != effectiveTombstoneId && !_memories.any((m) => m.id == pending.id)) {
        _memories.add(pending);
      }
    }
    // Persist the complete server projection, including optional temporal
    // fields, so restart/offline rendering does not silently lose the
    // server's assessment clock or evidence date.
    SharedPreferencesUtil().cachedMemories = List<Memory>.unmodifiable(
      _memories,
    );
    _revertOperationIds.removeWhere(
      (memoryId, _) => !_memories.any(
        (memory) => memory.id == memoryId && canRevertSupersededFact(memory),
      ),
    );

    _loading = false;
    _hasLoaded = true;
    _setCategories();
  }

  Future<void> loadMoreHistory({int limit = 500}) async {
    if (_filterThisDeviceOnly || !_ledgerHistorySupported || !_ledgerHistoryHasMore) {
      return;
    }
    if (_loadingMoreHistory) return;
    _loadingMoreHistory = true;
    try {
      final generation = _sessionGeneration;
      final cursor = _ledgerHistoryNextCursor;
      final result = await _fetchHistoryPage(
        limit: limit,
        offset: _ledgerHistoryOffset,
        cursor: cursor,
      );
      // Continuation pages carry the same capability contract as the initial
      // page; do not let a stale true value survive a missing/false header.
      if (generation != _sessionGeneration) return;
      _beliefEnabled = result.beliefEnabled;
      if (!result.supported) return;

      final existing = _memories.map((memory) => memory.id).toSet();
      _memories.addAll(
        result.memories.where((memory) => existing.add(memory.id)),
      );
      _ledgerHistoryOffset += result.memories.length;
      _ledgerHistoryNextCursor = result.nextCursor;
      _ledgerHistoryHasMore =
          result.nextCursor != null || result.truncated || (cursor == null && result.memories.length >= limit);
      _ledgerHistoryTruncated = result.truncated || _ledgerHistoryHasMore;
      _setCategories();
    } finally {
      _loadingMoreHistory = false;
    }
  }

  /// Sync pending memories to server when online
  Future<void> syncPendingMemories() async {
    if (_isSyncing) return;
    final generation = _sessionGeneration;
    final ownerUid = SharedPreferencesUtil().uid;
    if (ownerUid.isEmpty) return;

    final pendingMemories = SharedPreferencesUtil().pendingMemories.where((memory) => memory.uid == ownerUid).toList();
    if (pendingMemories.isEmpty) return;

    _isSyncing = true;
    Logger.debug(
      'MemoriesProvider: Syncing ${pendingMemories.length} pending memories...',
    );

    for (var memory in List.from(pendingMemories)) {
      if (generation != _sessionGeneration) return;
      try {
        final serverMemory = await createMemoryServer(
          memory.content,
          memory.visibility.name,
          memory.category.name,
        );

        if (serverMemory != null) {
          SharedPreferencesUtil().removePendingMemory(
            memory.id,
            ownerUid: ownerUid,
          );
          if (generation != _sessionGeneration) return;
          final idx = _memories.indexWhere((m) => m.id == memory.id);
          if (idx != -1) {
            // Keep the authoritative server projection, including temporal
            // assessment fields that are absent from an offline draft.
            _memories[idx] = serverMemory;
          }
        }
        if (generation != _sessionGeneration) return;
      } catch (e) {
        Logger.debug(
          'MemoriesProvider: Failed to sync memory ${memory.id}: $e',
        );
        // Keep in pending list for next sync attempt
      }
    }

    if (generation == _sessionGeneration) {
      _isSyncing = false;
      SharedPreferencesUtil().cachedMemories = List<Memory>.unmodifiable(
        _memories,
      );
      notifyListeners();
    }
  }

  /// Apply an explicit user review through canonical backend authority.
  ///
  /// The local change is optimistic so the control responds immediately, but
  /// it is rolled back if the server rejects or cannot persist the decision.
  ///
  /// A memory that is not in the loaded list (cold provider, truncated bulk
  /// list, or a recap referencing an id this client never paged in) is still
  /// reviewed by id: the request is id-addressed and the server stays the
  /// authority, so refusing to send it would strand the recap controls.
  Future<bool> reviewMemory(Memory memory, bool value) async {
    // Locked rows are immutable everywhere, including cache misses: the flag
    // travels on the memory itself, so a row absent from the loaded list is
    // still refused before any request is sent.
    if (memory.isLocked) return false;
    final index = _memories.indexWhere(
      (candidate) => candidate.id == memory.id,
    );
    if (index == -1) {
      final generation = _sessionGeneration;
      try {
        final persisted = await _reviewMemoryRequest(memory.id, value);
        if (generation != _sessionGeneration || !persisted) return false;
        // No live row will ever answer for this id from the loaded list, so
        // remember the persisted verdict for recap rows reading this id. A
        // live row (a later refresh, another surface) still wins: this map is
        // only consulted when the id does not resolve.
        _settledUnresolvedReviews[memory.id] = value;
        notifyListeners();
        return true;
      } catch (error) {
        Logger.warning(
          'MemoriesProvider: review persistence failed for ${memory.id}: $error',
        );
        return false;
      }
    }
    final generation = _sessionGeneration;
    final previousReview = memory.userReview;
    final previousReviewed = memory.reviewed;
    memory.userReview = value;
    memory.reviewed = true;
    notifyListeners();

    bool persisted;
    try {
      persisted = await _reviewMemoryRequest(memory.id, value);
    } catch (error) {
      Logger.warning(
        'MemoriesProvider: review persistence failed for ${memory.id}: $error',
      );
      persisted = false;
    }
    if (generation != _sessionGeneration) return false;
    if (!persisted) {
      memory.userReview = previousReview;
      memory.reviewed = previousReviewed;
      notifyListeners();
      return false;
    }
    return true;
  }

  /// Record an owner decision about whether this memory may be used by agents.
  ///
  /// The feedback id is minted once per memory/action and retained across
  /// retries so a lost response cannot create a second durable receipt. The
  /// response is followed by a normal list refresh; the local argument bag is
  /// only a short-lived fallback for offline/error rendering and is replaced
  /// by the next authenticated server projection when available.
  Future<bool> setMemoryUse(Memory memory, MemoryUseAction action) async {
    if (memory.isLocked ||
        memory.deleted ||
        memory.invalidAt != null ||
        (memory.supersededBy ?? '').trim().isNotEmpty ||
        (memory.ledgerStatus != null && memory.ledgerStatus != 'active') ||
        (memory.isKnowledgeLedger && !memory.isCurrentKnowledgeLedgerRow) ||
        _beliefEnabled != true) {
      return false;
    }
    final operationKey = '${memory.id}:${action.apiValue}';
    if (!_memoryUseInFlight.add(memory.id)) return false;
    final generation = _sessionGeneration;
    final feedbackId = _memoryUseFeedbackIds.putIfAbsent(
      operationKey,
      () => const Uuid().v4(),
    );
    notifyListeners();

    try {
      final result = await _memoryUseRequest(
        memoryId: memory.id,
        action: action,
        feedbackId: feedbackId,
      );
      if (!result.persisted || generation != _sessionGeneration) return false;

      final index = _memories.indexWhere(
        (candidate) => candidate.id == memory.id,
      );
      if (index != -1 && result.suppressed != null) {
        final live = _memories[index];
        final arguments = Map<String, dynamic>.from(live.arguments ?? const {});
        final existing = arguments['memory_use'];
        final use = existing is Map ? Map<String, dynamic>.from(existing) : <String, dynamic>{};
        use['suppressed'] = result.suppressed;
        use['last_action'] = (result.action ?? action).apiValue;
        use['state'] = result.suppressed == true
            ? 'suppressed'
            : ((result.action ?? action) == MemoryUseAction.useful ? 'useful' : 'allowed');
        use['feedback_id'] = result.feedbackId ?? feedbackId;
        arguments['memory_use'] = use;
        live.arguments = arguments;
      }
      // Preserve the confirmed receipt if a refresh is unavailable, then
      // replace it with the server's full current projection when it is.
      SharedPreferencesUtil().cachedMemories = List<Memory>.unmodifiable(
        _memories,
      );
      try {
        // A load may already be in flight from before this owner action. It
        // cannot be reused as confirmation because it predates the mutation.
        await _loadMemoriesFresh();
        // A later click is a distinct user action; only retries of an
        // unacknowledged action reuse its id. Keep it when refresh fails so a
        // retry still converges on the acknowledged server receipt.
        if (!_loadFailed) _memoryUseFeedbackIds.remove(operationKey);
      } catch (error) {
        Logger.warning(
          'MemoriesProvider: memory-use refresh failed for ${memory.id}: $error',
        );
      }
      return true;
    } catch (error) {
      Logger.warning(
        'MemoriesProvider: memory-use persistence failed for ${memory.id}: $error',
      );
      return false;
    } finally {
      _memoryUseInFlight.remove(memory.id);
      notifyListeners();
    }
  }

  /// Append an authoritative current replacement for one superseded v1 fact.
  ///
  /// This is deliberately non-optimistic: the historical row remains
  /// untouched and no replacement becomes visible until the backend returns a
  /// fully validated canonical row. A session change discards the late result.
  Future<bool> revertSupersededFact(Memory memory) async {
    final sourceIndex = _memories.indexWhere(
      (candidate) => candidate.id == memory.id,
    );
    if (sourceIndex == -1 || !canRevertSupersededFact(memory) || isRevertingMemory(memory.id)) {
      return false;
    }

    final generation = _sessionGeneration;
    if (!_revertingMemoryIds.add(memory.id)) return false;
    // Retain one idempotency key across all ambiguous failures. A transport
    // error or lost response may follow a committed append; rotating the key
    // would let a user retry append the same historical value again.
    final operationId = _revertOperationIds.putIfAbsent(
      memory.id,
      () => const Uuid().v4(),
    );
    notifyListeners();

    try {
      RevertMemoryResult result;
      try {
        result = await _revertMemoryRequest(memory.id, operationId);
      } catch (error) {
        Logger.warning(
          'MemoriesProvider: fact revert failed for ${memory.id}: $error',
        );
        return false;
      }
      if (generation != _sessionGeneration || !result.persisted) return false;

      final currentSourceIndex = _memories.indexWhere(
        (candidate) => candidate.id == memory.id,
      );
      if (currentSourceIndex == -1 ||
          !_isEligibleSupersededFact(_memories[currentSourceIndex]) ||
          !_sameRevertSource(memory, _memories[currentSourceIndex])) {
        return false;
      }
      final currentSource = _memories[currentSourceIndex];
      final replacement = result.authoritativeMemory;
      final currentTail = _matchingCurrentTail(currentSource);
      if (replacement == null ||
          !_isAuthoritativeRevertReplacement(
            currentSource,
            replacement,
            expectedVisibility: currentTail?.visibility,
          )) {
        return false;
      }

      final existingReplacementIndex = _memories.indexWhere(
        (candidate) => candidate.id == replacement.id,
      );
      if (existingReplacementIndex != -1 &&
          !_sameAuthoritativeReplacement(
            _memories[existingReplacementIndex],
            replacement,
          )) {
        return false;
      }

      final staleCurrentTail = currentTail?.id == replacement.id ? null : currentTail;
      _ledgerProjectionRevision++;

      // The backend atomically closes the current tail when it appends the
      // restored row. Remove that known-stale current projection before
      // exposing the replacement; do not forge lifecycle fields locally.
      if (staleCurrentTail != null) {
        _memories.removeWhere(
          (candidate) => candidate.id == staleCurrentTail.id,
        );
      }
      if (existingReplacementIndex == -1) {
        _memories.add(replacement);
      }
      _setCategories();
      await _refreshLedgerHistoryAfterRevert(
        generation,
        closedTailId: staleCurrentTail?.id,
        replacementId: replacement.id,
      );
      _revertOperationIds.remove(memory.id);
      return true;
    } finally {
      final removed = _revertingMemoryIds.remove(memory.id);
      if (removed && generation == _sessionGeneration) notifyListeners();
    }
  }

  Future<void> _refreshLedgerHistoryAfterRevert(
    int generation, {
    required String? closedTailId,
    required String replacementId,
  }) async {
    if (_filterThisDeviceOnly || closedTailId == null || generation != _sessionGeneration) {
      return;
    }

    try {
      const historyPageSize = 500;
      const maxHistoryPages = 10;
      var historyOffset = 0;
      final refreshedHistory = <String, Memory>{};
      for (var page = 0; page < maxHistoryPages; page++) {
        final result = await _fetchLedgerHistoryRequest(
          limit: historyPageSize,
          offset: historyOffset,
        );
        if (generation != _sessionGeneration || !result.supported) return;
        for (final row in result.memories) {
          if (row.id != replacementId && row.isHistoricalKnowledgeLedgerRow) {
            refreshedHistory[row.id] = row;
          }
        }
        if (result.truncated || result.memories.length < historyPageSize) break;
        historyOffset += result.memories.length;
      }
      if (generation != _sessionGeneration) return;
      for (final row in refreshedHistory.values) {
        final index = _memories.indexWhere(
          (candidate) => candidate.id == row.id,
        );
        if (index == -1) {
          _memories.add(row);
        } else {
          _memories[index] = row;
        }
      }
      _setCategories();
    } catch (error) {
      Logger.warning(
        'MemoriesProvider: ledger history refresh failed after fact revert: $error',
      );
    }
  }

  static bool _sameRevertSource(Memory requested, Memory current) {
    return requested.id == current.id &&
        requested.uid == current.uid &&
        requested.content == current.content &&
        requested.ledgerSchemaVersion == current.ledgerSchemaVersion &&
        requested.ledgerKind == current.ledgerKind &&
        requested.ledgerSlot == current.ledgerSlot &&
        requested.subjectScope == current.subjectScope &&
        requested.subjectEntityId == current.subjectEntityId &&
        requested.supersededBy == current.supersededBy &&
        requested.invalidAt == current.invalidAt &&
        requested.curationWeight == current.curationWeight &&
        requested.userReview == current.userReview;
  }

  Memory? _matchingCurrentTail(Memory source) {
    final seen = <String>{source.id};
    var successorId = (source.supersededBy ?? '').trim();
    while (successorId.isNotEmpty && seen.add(successorId)) {
      final matches = _memories.where((candidate) => candidate.id == successorId).toList(growable: false);
      if (matches.length != 1) break;
      final successor = matches.single;
      if (successor.isCurrentKnowledgeLedgerRow && successor.ledgerKind == KnowledgeLedgerKind.fact) {
        return successor;
      }
      successorId = (successor.supersededBy ?? '').trim();
    }

    // A bounded history page may omit an intermediate link. Never guess the
    // tail from slot/subject identity: active-row uniqueness is not a client
    // invariant, and removing a guessed row could hide unrelated knowledge.
    return null;
  }

  static bool _isAuthoritativeRevertReplacement(
    Memory source,
    Memory replacement, {
    MemoryVisibility? expectedVisibility,
  }) {
    return replacement.id.trim().isNotEmpty &&
        replacement.id != source.id &&
        replacement.uid == source.uid &&
        replacement.ledgerSchemaVersion == 'knowledge_ledger.v1' &&
        replacement.ledgerKind == KnowledgeLedgerKind.fact &&
        replacement.intentBacked &&
        replacement.writeReason == 'direct_user_statement' &&
        !replacement.deleted &&
        !replacement.isLocked &&
        replacement.userReview != false &&
        replacement.validAt != null &&
        replacement.invalidAt == null &&
        (replacement.supersededBy ?? '').trim().isEmpty &&
        replacement.content.trim() == source.content.trim() &&
        replacement.ledgerSlot == source.ledgerSlot &&
        replacement.subjectScope == source.subjectScope &&
        replacement.subjectEntityId == source.subjectEntityId &&
        replacement.curationWeight == source.curationWeight &&
        replacement.evidence.any(
          (evidence) => evidence['source_type'] == 'explicit_user_revert' && evidence['source_id'] == source.id,
        ) &&
        (expectedVisibility == null || replacement.visibility == expectedVisibility);
  }

  static bool _sameAuthoritativeReplacement(Memory current, Memory returned) {
    return current.id == returned.id &&
        current.uid == returned.uid &&
        current.content == returned.content &&
        current.ledgerSchemaVersion == returned.ledgerSchemaVersion &&
        current.ledgerKind == returned.ledgerKind &&
        current.ledgerSlot == returned.ledgerSlot &&
        current.subjectScope == returned.subjectScope &&
        current.subjectEntityId == returned.subjectEntityId &&
        current.curationWeight == returned.curationWeight &&
        current.visibility == returned.visibility &&
        current.validAt == returned.validAt &&
        current.supersededBy == returned.supersededBy &&
        current.invalidAt == returned.invalidAt &&
        current.intentBacked == returned.intentBacked &&
        current.writeReason == returned.writeReason &&
        current.userReview == returned.userReview;
  }

  Memory? _lastDeletedMemory;
  Timer? _deletionTimer;
  String? _pendingDeletionId;

  Memory? get lastDeletedMemory => _lastDeletedMemory;

  void deleteMemory(Memory memory) {
    _cancelDeletionTimer();

    _lastDeletedMemory = memory;
    _pendingDeletionId = memory.id;

    _memories.remove(memory);
    _setCategories();
    notifyListeners();

    _startDeletionTimer();
  }

  void _cancelDeletionTimer() {
    if (_deletionTimer != null && _deletionTimer!.isActive) {
      _deletionTimer!.cancel();
      _deletionTimer = null;
    }
  }

  void _startDeletionTimer() {
    _deletionTimer = Timer(const Duration(seconds: 4), () async {
      await _finalizeDeletion();
    });
  }

  Future<void> _finalizeDeletion() async {
    if (_pendingDeletionId == null) {
      _lastDeletedMemory = null;
      return;
    }

    final id = _pendingDeletionId!;

    final deletedMemory = _lastDeletedMemory;
    var deleteSucceeded = true;

    // If memory was created offline and not yet synced
    if (SharedPreferencesUtil().pendingMemories.any((m) => m.id == id)) {
      SharedPreferencesUtil().removePendingMemory(id);
    } else {
      // Memory exists on server
      try {
        deleteSucceeded = await _deleteMemoryRequest(id);
      } catch (e) {
        Logger.debug('MemoriesProvider: Failed to delete memory $id: $e');
        deleteSucceeded = false;
      }
    }

    if (!deleteSucceeded && _pendingDeletionId == id && deletedMemory?.id == id) {
      if (!_memories.any((memory) => memory.id == id)) {
        _memories.add(deletedMemory!);
      }
      _setCategories();
      notifyListeners();
    }

    if (_pendingDeletionId == id) {
      _pendingDeletionId = null;
      _lastDeletedMemory = null;
    }
  }

  Future<void> confirmPendingDeletion() async {
    _cancelDeletionTimer();
    await _finalizeDeletion();
  }

  // Restore the last deleted memory
  Future<bool> restoreLastDeletedMemory() async {
    if (_lastDeletedMemory == null) return false;

    _cancelDeletionTimer();
    _pendingDeletionId = null;

    _memories.add(_lastDeletedMemory!);
    _lastDeletedMemory = null;

    _setCategories();
    notifyListeners();

    return true;
  }

  void deleteAllMemories() async {
    final int countBeforeDeletion = _memories.length;
    await deleteAllMemoriesServer();
    _memories.clear();
    if (countBeforeDeletion > 0) {
      PlatformManager.instance.analytics.memoriesAllDeleted(
        countBeforeDeletion,
      );
    }
    _setCategories();
  }

  /// Create a memory - works offline by saving locally first, then syncing
  Future<bool> createMemory(
    String content, [
    MemoryVisibility visibility = MemoryVisibility.public,
    MemoryCategory category = MemoryCategory.manual,
  ]) async {
    final generation = _sessionGeneration;
    final ownerUid = SharedPreferencesUtil().uid;
    if (ownerUid.isEmpty) return false;
    // Create the memory object first
    final newMemory = Memory(
      id: const Uuid().v4(),
      uid: ownerUid,
      content: content,
      category: category,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      conversationId: null,
      reviewed: false,
      manuallyAdded: true,
      visibility: visibility,
    );

    // Add to local list immediately (optimistic update)
    _memories.add(newMemory);
    _setCategories();
    notifyListeners();

    // Save to pending memories for persistence across app restarts
    SharedPreferencesUtil().addPendingMemory(newMemory);

    // Try to sync to server immediately
    final serverMemory = await createMemoryServer(
      content,
      visibility.name,
      category.name,
    );

    if (serverMemory != null) {
      // Remove from the original account's pending queue even if the visible
      // session changed while the request was in flight.
      SharedPreferencesUtil().removePendingMemory(
        newMemory.id,
        ownerUid: ownerUid,
      );
      if (generation != _sessionGeneration) return true;
      final idx = _memories.indexWhere((m) => m.id == newMemory.id);
      if (idx != -1) {
        _memories[idx].id = serverMemory.id;
      }
    }
    if (generation != _sessionGeneration) return true;

    // Return true since memory is saved locally regardless of server sync
    return true;
  }

  Future<void> updateMemoryVisibility(
    Memory memory,
    MemoryVisibility visibility,
  ) async {
    await updateMemoryVisibilityServer(memory.id, visibility.name);

    final idx = _memories.indexWhere((m) => m.id == memory.id);
    if (idx != -1) {
      Memory memoryToUpdate = _memories[idx];
      memoryToUpdate.visibility = visibility;
      _memories[idx] = memoryToUpdate;

      PlatformManager.instance.analytics.memoryVisibilityChanged(
        memoryToUpdate,
        visibility,
      );
      _setCategories();
    }
  }

  Future<bool> toggleMemoryBaseline(Memory memory, bool isBaseline) async {
    final success = await updateMemoryBaselineServer(memory.id, isBaseline);

    if (success) {
      final idx = _memories.indexWhere((m) => m.id == memory.id);
      if (idx != -1) {
        _memories[idx].isBaseline = isBaseline;
        notifyListeners();
        _setCategories();
      }
    }
    return success;
  }

  Future<bool> editMemory(
    Memory memory,
    String value, [
    MemoryCategory? category,
  ]) async {
    if (memory.isKnowledgeLedger &&
        (memory.deleted ||
            memory.invalidAt != null ||
            (memory.supersededBy ?? '').trim().isNotEmpty ||
            memory.ledgerKind != KnowledgeLedgerKind.fact ||
            memory.isLocked)) {
      return false;
    }
    final result = await _editMemoryRequest(memory.id, value);

    if (result.persisted) {
      final idx = _memories.indexWhere((m) => m.id == memory.id);
      if (idx != -1) {
        if (memory.isKnowledgeLedger) {
          final replacement = result.authoritativeMemory;
          if (replacement == null ||
              !replacement.isKnowledgeLedger ||
              replacement.uid != memory.uid ||
              replacement.id == memory.id ||
              replacement.content.trim() != value.trim() ||
              replacement.deleted ||
              replacement.invalidAt != null ||
              (replacement.supersededBy ?? '').trim().isNotEmpty ||
              replacement.ledgerKind != KnowledgeLedgerKind.fact ||
              !replacement.intentBacked ||
              replacement.isLocked ||
              replacement.ledgerSlot != memory.ledgerSlot ||
              replacement.subjectScope != memory.subjectScope ||
              replacement.subjectEntityId != memory.subjectEntityId ||
              replacement.curationWeight != memory.curationWeight ||
              replacement.visibility != memory.visibility) {
            return false;
          }
          _memories[idx] = replacement;
        } else {
          memory.content = value;
          if (category != null) {
            memory.category = category;
          }
          memory.updatedAt = DateTime.now();
          memory.edited = true;
          _memories[idx] = memory;
        }

        _setCategories();
        notifyListeners();
      }
    }

    return result.persisted;
  }

  Future<void> updateAllMemoriesVisibility(bool makePrivate) async {
    final visibility = makePrivate ? MemoryVisibility.private : MemoryVisibility.public;
    int updatedCount = 0;
    List<Memory> memoriesSuccessfullyUpdated = [];

    for (var memory in List.from(_memories)) {
      if (memory.visibility != visibility) {
        try {
          await updateMemoryVisibilityServer(memory.id, visibility.name);
          final idx = _memories.indexWhere((m) => m.id == memory.id);
          if (idx != -1) {
            _memories[idx].visibility = visibility;
            memoriesSuccessfullyUpdated.add(_memories[idx]);
            updatedCount++;
          }
        } catch (e) {
          print('Failed to update visibility for memory ${memory.id}: $e');
        }
      }
    }

    if (updatedCount > 0) {
      PlatformManager.instance.analytics.memoriesAllVisibilityChanged(
        visibility,
        updatedCount,
      );
    }

    _setCategories();
  }
}
