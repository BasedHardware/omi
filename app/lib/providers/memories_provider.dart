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

typedef FetchMemoriesRequest = Future<GetMemoriesResult> Function({int limit, int offset, bool thisDeviceOnly});
typedef FetchLedgerHistoryRequest = Future<GetLedgerHistoryResult> Function({int limit, int offset});
typedef ReviewMemoryRequest = Future<bool> Function(String memoryId, bool value);
typedef EditMemoryRequest = Future<EditMemoryResult> Function(String memoryId, String value);
typedef RevertMemoryRequest = Future<RevertMemoryResult> Function(String memoryId, String operationId);

Future<GetLedgerHistoryResult> _noLedgerHistory({int limit = 500, int offset = 0}) async =>
    const GetLedgerHistoryResult([], supported: false);

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
  final FetchLedgerHistoryRequest _fetchLedgerHistoryRequest;
  final Future<bool> Function(String) _deleteMemoryRequest;
  final ReviewMemoryRequest _reviewMemoryRequest;
  final EditMemoryRequest _editMemoryRequest;
  final RevertMemoryRequest _revertMemoryRequest;
  final Set<String> _revertingMemoryIds = {};
  final Map<String, String> _revertOperationIds = {};

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

  MemoriesProvider({
    FetchMemoriesRequest? fetchMemoriesRequest,
    FetchLedgerHistoryRequest? fetchLedgerHistoryRequest,
    Future<bool> Function(String)? deleteMemoryRequest,
    ReviewMemoryRequest? reviewMemoryRequest,
    EditMemoryRequest? editMemoryRequest,
    RevertMemoryRequest? revertMemoryRequest,
  })  : _fetchMemoriesRequest = fetchMemoriesRequest ?? getMemoriesResult,
        _fetchLedgerHistoryRequest =
            fetchLedgerHistoryRequest ?? (fetchMemoriesRequest == null ? getLedgerHistory : _noLedgerHistory),
        _deleteMemoryRequest = deleteMemoryRequest ?? deleteMemoryServer,
        _reviewMemoryRequest = reviewMemoryRequest ?? reviewMemoryServer,
        _editMemoryRequest = editMemoryRequest ?? editMemoryServer,
        _revertMemoryRequest = revertMemoryRequest ?? revertMemoryServer;

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
      .where((memory) => memory.isCurrentKnowledgeLedgerRow && memory.ledgerKind == KnowledgeLedgerKind.fact)
      .toList(growable: false)
    ..sort(_ledgerOrder);

  List<Memory> get currentLedgerPlaybooks =>
      _memories.where((memory) => memory.isCurrentKnowledgeLedgerRow && memory.isLedgerPlaybook).toList(growable: false)
        ..sort(_ledgerOrder);

  List<Memory> get currentLedgerTriggers =>
      _memories.where((memory) => memory.isCurrentKnowledgeLedgerRow && memory.isLedgerTrigger).toList(growable: false)
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
    final validAt = (a.validAt ?? a.updatedAt).compareTo(b.validAt ?? b.updatedAt);
    if (validAt != 0) return validAt;
    return a.id.compareTo(b.id);
  }

  List<Memory> get filteredMemories {
    return _memories.where((memory) {
      // Apply search filter
      final matchesSearch =
          _searchQuery.isEmpty || memory.content.decodeString.toLowerCase().contains(_searchQuery.toLowerCase());

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

      return matchesSearch && categoryMatch && deviceMatch;
    }).toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
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
    await prefs.setStringList('memories_filter_categories', _selectedCategories.map((e) => e.name).toList());
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
    categories = [];
    selectedCategory = null;
    _loading = false;
    _hasLoaded = false;
    _loadFailed = false;
    _isSyncing = false;
    _revertingMemoryIds.clear();
    _revertOperationIds.clear();
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
    await _ensureClientDeviceInitialized();
    if (generation != _sessionGeneration) return;
    await _loadFilter();
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
          .map((e) => MemoryCategory.values.firstWhere((c) => c.name == e, orElse: () => MemoryCategory.system))
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
    if (inFlight != null && _inFlightLoadLimit == limit && _inFlightLoadDeviceScoped == _filterThisDeviceOnly) {
      try {
        await inFlight;
      } catch (_) {}
      return;
    }
    final loadFuture = _loadMemoriesInternal(limit: limit);
    _inFlightLoad = loadFuture;
    _inFlightLoadLimit = limit;
    _inFlightLoadDeviceScoped = _filterThisDeviceOnly;
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
    final ledgerProjectionRevision = _ledgerProjectionRevision;
    // Snapshot the pending-deletion ID before any await: a refresh that
    // started during the undo window must still suppress the deleted item
    // even if _finalizeDeletion() clears the field while the fetch is in
    // flight.
    final tombstoneId = _pendingDeletionId;
    _loading = true;
    notifyListeners();

    if (_filterThisDeviceOnly) {
      await _ensureClientDeviceInitialized();
      if (generation != _sessionGeneration || loadSequence != _loadSequence) {
        return;
      }
    }

    // Page until a short page: backend no longer expands the first page to 5000
    // (prod GET /v3/memories 504s). Cap total fetch so a huge account cannot hang the UI.
    const maxPages = 20;
    final all = <Memory>[];
    var offset = 0;
    var deviceScopeSupported = true;
    var ledgerHistorySupported = false;
    var ledgerHistoryTruncated = false;
    for (var page = 0; page < maxPages; page++) {
      final result = await _fetchMemoriesRequest(limit: limit, offset: offset, thisDeviceOnly: _filterThisDeviceOnly);
      if (generation != _sessionGeneration || loadSequence != _loadSequence) {
        return;
      }
      if (!result.ok) {
        _loadFailed = true;
        _loading = false;
        _hasLoaded = true;
        notifyListeners();
        return;
      }
      deviceScopeSupported = result.deviceScopeSupported;
      all.addAll(result.memories);
      // A truncated page is an honest partial response with no resumable cursor;
      // stop loading instead of continuing with an unstable offset.
      if (result.truncated || result.memories.length < limit) {
        if (result.truncated) {
          Logger.warning('MemoriesProvider: server returned a truncated list; stopping at $offset rows');
        }
        break;
      }
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
      for (var page = 0; page < maxHistoryPages; page++) {
        final result = await _fetchLedgerHistoryRequest(limit: historyPageSize, offset: historyOffset);
        if (generation != _sessionGeneration || loadSequence != _loadSequence) return;
        ledgerHistorySupported = result.supported;
        if (!result.supported) break;
        all.addAll(result.memories.where((memory) => seen.add(memory.id)));
        historyRowsLoaded += result.memories.length;
        if (result.truncated || result.memories.length < historyPageSize) {
          ledgerHistoryTruncated = result.truncated;
          break;
        }
        historyOffset += result.memories.length;
        if (page == maxHistoryPages - 1) ledgerHistoryTruncated = true;
      }
      if (ledgerHistoryTruncated) {
        Logger.warning('MemoriesProvider: ledger history is partial; loaded $historyRowsLoaded rows');
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
    _loadFailed = false;

    // Merge pending memories that haven't synced yet
    final pendingMemories = SharedPreferencesUtil().pendingMemories;
    for (var pending in pendingMemories) {
      if (pending.id != effectiveTombstoneId && !_memories.any((m) => m.id == pending.id)) {
        _memories.add(pending);
      }
    }
    _revertOperationIds.removeWhere(
      (memoryId, _) => !_memories.any((memory) => memory.id == memoryId && canRevertSupersededFact(memory)),
    );

    _loading = false;
    _hasLoaded = true;
    _setCategories();
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
    Logger.debug('MemoriesProvider: Syncing ${pendingMemories.length} pending memories...');

    for (var memory in List.from(pendingMemories)) {
      if (generation != _sessionGeneration) return;
      try {
        final serverMemory = await createMemoryServer(memory.content, memory.visibility.name, memory.category.name);

        if (serverMemory != null) {
          SharedPreferencesUtil().removePendingMemory(memory.id, ownerUid: ownerUid);
          if (generation != _sessionGeneration) return;
          final idx = _memories.indexWhere((m) => m.id == memory.id);
          if (idx != -1) {
            _memories[idx].id = serverMemory.id;
          }
        }
        if (generation != _sessionGeneration) return;
      } catch (e) {
        Logger.debug('MemoriesProvider: Failed to sync memory ${memory.id}: $e');
        // Keep in pending list for next sync attempt
      }
    }

    if (generation == _sessionGeneration) {
      _isSyncing = false;
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
    final index = _memories.indexWhere((candidate) => candidate.id == memory.id);
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
        Logger.warning('MemoriesProvider: review persistence failed for ${memory.id}: $error');
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
      Logger.warning('MemoriesProvider: review persistence failed for ${memory.id}: $error');
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

  /// Append an authoritative current replacement for one superseded v1 fact.
  ///
  /// This is deliberately non-optimistic: the historical row remains
  /// untouched and no replacement becomes visible until the backend returns a
  /// fully validated canonical row. A session change discards the late result.
  Future<bool> revertSupersededFact(Memory memory) async {
    final sourceIndex = _memories.indexWhere((candidate) => candidate.id == memory.id);
    if (sourceIndex == -1 || !canRevertSupersededFact(memory) || isRevertingMemory(memory.id)) return false;

    final generation = _sessionGeneration;
    if (!_revertingMemoryIds.add(memory.id)) return false;
    // Retain one idempotency key across all ambiguous failures. A transport
    // error or lost response may follow a committed append; rotating the key
    // would let a user retry append the same historical value again.
    final operationId = _revertOperationIds.putIfAbsent(memory.id, () => const Uuid().v4());
    notifyListeners();

    try {
      RevertMemoryResult result;
      try {
        result = await _revertMemoryRequest(memory.id, operationId);
      } catch (error) {
        Logger.warning('MemoriesProvider: fact revert failed for ${memory.id}: $error');
        return false;
      }
      if (generation != _sessionGeneration || !result.persisted) return false;

      final currentSourceIndex = _memories.indexWhere((candidate) => candidate.id == memory.id);
      if (currentSourceIndex == -1 ||
          !_isEligibleSupersededFact(_memories[currentSourceIndex]) ||
          !_sameRevertSource(memory, _memories[currentSourceIndex])) {
        return false;
      }
      final currentSource = _memories[currentSourceIndex];
      final replacement = result.authoritativeMemory;
      final currentTail = _matchingCurrentTail(currentSource);
      if (replacement == null ||
          !_isAuthoritativeRevertReplacement(currentSource, replacement, expectedVisibility: currentTail?.visibility)) {
        return false;
      }

      final existingReplacementIndex = _memories.indexWhere((candidate) => candidate.id == replacement.id);
      if (existingReplacementIndex != -1 &&
          !_sameAuthoritativeReplacement(_memories[existingReplacementIndex], replacement)) {
        return false;
      }

      final staleCurrentTail = currentTail?.id == replacement.id ? null : currentTail;
      _ledgerProjectionRevision++;

      // The backend atomically closes the current tail when it appends the
      // restored row. Remove that known-stale current projection before
      // exposing the replacement; do not forge lifecycle fields locally.
      if (staleCurrentTail != null) {
        _memories.removeWhere((candidate) => candidate.id == staleCurrentTail.id);
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
    if (_filterThisDeviceOnly || closedTailId == null || generation != _sessionGeneration) return;

    try {
      const historyPageSize = 500;
      const maxHistoryPages = 10;
      var historyOffset = 0;
      final refreshedHistory = <String, Memory>{};
      for (var page = 0; page < maxHistoryPages; page++) {
        final result = await _fetchLedgerHistoryRequest(limit: historyPageSize, offset: historyOffset);
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
        final index = _memories.indexWhere((candidate) => candidate.id == row.id);
        if (index == -1) {
          _memories.add(row);
        } else {
          _memories[index] = row;
        }
      }
      _setCategories();
    } catch (error) {
      Logger.warning('MemoriesProvider: ledger history refresh failed after fact revert: $error');
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
      PlatformManager.instance.analytics.memoriesAllDeleted(countBeforeDeletion);
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
    final serverMemory = await createMemoryServer(content, visibility.name, category.name);

    if (serverMemory != null) {
      // Remove from the original account's pending queue even if the visible
      // session changed while the request was in flight.
      SharedPreferencesUtil().removePendingMemory(newMemory.id, ownerUid: ownerUid);
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

  Future<void> updateMemoryVisibility(Memory memory, MemoryVisibility visibility) async {
    await updateMemoryVisibilityServer(memory.id, visibility.name);

    final idx = _memories.indexWhere((m) => m.id == memory.id);
    if (idx != -1) {
      Memory memoryToUpdate = _memories[idx];
      memoryToUpdate.visibility = visibility;
      _memories[idx] = memoryToUpdate;

      PlatformManager.instance.analytics.memoryVisibilityChanged(memoryToUpdate, visibility);
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

  Future<bool> editMemory(Memory memory, String value, [MemoryCategory? category]) async {
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
      PlatformManager.instance.analytics.memoriesAllVisibilityChanged(visibility, updatedCount);
    }

    _setCategories();
  }
}
