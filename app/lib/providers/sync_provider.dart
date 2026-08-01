import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/conversation_sync_utils.dart';
import 'package:omi/utils/waveform_utils.dart';

enum WalStatusFilter { pending, synced, corrupted }

enum WalDisplayFilter { all, pending, synced }

class SyncProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  // Services
  final AudioPlayerUtils _audioPlayerUtils = AudioPlayerUtils.instance;
  final IWalService? _walServiceOverride;
  final SyncUploadGate _uploadGate;
  final bool _startBackgroundSync;
  final Future<void> Function(LocalWalSyncImpl phone) _waitForWalReady;
  final Future<void> Function() _startRecovery;
  final Future<void> Function(WakeTrigger trigger) _wakeTransfer;

  /// Completes after WAL loading and startup fair-use reconciliation finish.
  @visibleForTesting
  late final Future<void> initialized;

  // WAL management
  List<Wal> _allWals = [];
  List<Wal> get allWals => _allWals;
  bool _isLoadingWals = false;
  bool get isLoadingWals => _isLoadingWals;

  // Memoization cache for displaySortedWals — see getter below.
  List<Wal>? _sortedCache;
  int _sortedCacheStamp = 0;

  // Storage filter
  WalStorage? _storageFilter;
  WalStorage? get storageFilter => _storageFilter;

  // Status filter (used by SyncPage)
  WalStatusFilter _statusFilter = WalStatusFilter.pending;
  WalStatusFilter get statusFilter => _statusFilter;

  void setStatusFilter(WalStatusFilter filter) {
    _statusFilter = filter;
    notifyListeners();
  }

  // `uploaded` is not yet backed up (the server job is still processing), so
  // it counts as pending — keeps it visible in the legacy SyncPage and in
  // pending counts until the reconciler confirms it `synced`. `corrupted` is
  // terminal: retain it in All and Needs Attention, never present it as work
  // that sync can still complete.
  bool _isPending(Wal w) =>
      w.status != WalStatus.corrupted && (w.status == WalStatus.miss || w.status == WalStatus.uploaded || w.isSyncing);

  // Memoized status-filtered partitions of _allWals. Returning a stable
  // List<Wal> reference between rebuilds is load-bearing — downstream the
  // legacy SyncPage's OptimizedWalsListWidget stamps its grouped-flatten
  // cache off the input list's identity, so without stable refs here the
  // widget-level cache misses every rebuild and recomputes the sort.
  //
  // Invalidation: stamp = identityHashCode(_allWals) ^ _allWals.length.
  // This works because every wal-status mutation path in the codebase
  // (sdcard, flash, storage, local) flips state in place, then notifies
  // the provider, which calls refreshWals() to reassign _allWals from
  // the wal service (see refreshWals at the bottom of this class). The
  // new list has a new identityHashCode → stamp changes → cache invalidates.
  // In-place flips that don't go through refreshWals would not invalidate
  // — but there are none today; if any are added, route them through
  // refreshWals or bump a version counter here.
  //
  // All three partitions are computed in a single pass to avoid three iterations
  // over a potentially 50k-item list. All caches share the same stamp.
  List<Wal>? _pendingWalsCache;
  List<Wal>? _syncedWalsCache;
  List<Wal>? _corruptedWalsCache;
  int _filteredWalsCacheStamp = 0;

  void _ensureFilteredCaches() {
    final stamp = identityHashCode(_allWals) ^ _allWals.length;
    if (_pendingWalsCache != null && _filteredWalsCacheStamp == stamp) return;
    final pending = <Wal>[];
    final synced = <Wal>[];
    final corrupted = <Wal>[];
    for (final w in _allWals) {
      if (w.status == WalStatus.synced) {
        synced.add(w);
      } else if (w.status == WalStatus.corrupted) {
        corrupted.add(w);
      } else if (_isPending(w)) {
        pending.add(w);
      }
    }
    _pendingWalsCache = pending;
    _syncedWalsCache = synced;
    _corruptedWalsCache = corrupted;
    _filteredWalsCacheStamp = stamp;
  }

  List<Wal> get pendingWals {
    _ensureFilteredCaches();
    return _pendingWalsCache!;
  }

  List<Wal> get syncedWals {
    _ensureFilteredCaches();
    return _syncedWalsCache!;
  }

  /// Terminally unavailable recordings. They remain reachable for review or
  /// deletion, but never count as retryable pending work.
  List<Wal> get corruptedWals {
    _ensureFilteredCaches();
    return _corruptedWalsCache!;
  }

  List<Wal> get uploadedWals => _allWals.where((w) => w.status == WalStatus.uploaded).toList();

  List<Wal> get pendingDeletableWals => _allWals.where((w) => !w.isSyncing && w.status == WalStatus.miss).toList();

  // Count-only accessors for status-chip badges. Read length from the
  // shared cached partitions so the chips don't trigger an extra iteration
  // when the cache is already warm. Names disambiguate from the existing
  // `syncedWalsCount` / `syncingWalsCount` getters further down which key
  // off `syncDisplayState` (different semantic, auto-sync page surface).
  int get pendingStatusCount {
    _ensureFilteredCaches();
    return _pendingWalsCache!.length;
  }

  int get syncedStatusCount {
    _ensureFilteredCaches();
    return _syncedWalsCache!.length;
  }

  int get corruptedStatusCount {
    _ensureFilteredCaches();
    return _corruptedWalsCache!.length;
  }

  /// Recordings that the storage sheet's Clear All action can remove.
  int get clearableWalsCount => syncedWals.length + pendingDeletableWals.length + corruptedWals.length;

  /// True while a fair-use (429) cooldown is active — uploads are paused.
  bool get isRateLimited => SyncRateLimiter.instance.isLimited;
  DateTime? get rateLimitedUntil => SyncRateLimiter.instance.until;
  RateLimitReason? get rateLimitReason => SyncRateLimiter.instance.reason;

  List<Wal> get filteredByStatusWals {
    switch (_statusFilter) {
      case WalStatusFilter.pending:
        return pendingWals;
      case WalStatusFilter.synced:
        return syncedWals;
      case WalStatusFilter.corrupted:
        return corruptedWals;
    }
  }

  // ─────────────────────────────────────────
  // Redesigned auto-sync page: unified self-describing list
  // (additive — does not touch the legacy SyncPage API above)
  // ─────────────────────────────────────────

  /// All recordings, newest first. The redesigned list shows synced and
  /// unsynced recordings together so backed-up work is never hidden behind a
  /// tab the user has to discover.
  ///
  /// Memoized: re-sorts only when the underlying list reference or length
  /// changes. Sort key is `timerStart`, which is immutable per Wal, so
  /// in-place status mutations don't invalidate the order. With tens of
  /// thousands of wals and frequent `notifyListeners()` during active sync
  /// this avoids 5–15ms of redundant sort work per rebuild.
  List<Wal> get displaySortedWals {
    final stamp = identityHashCode(_allWals) ^ _allWals.length;
    final cached = _sortedCache;
    if (cached != null && _sortedCacheStamp == stamp) return cached;
    final list = List<Wal>.from(_allWals);
    list.sort((a, b) => b.timerStart.compareTo(a.timerStart));
    _sortedCache = list;
    _sortedCacheStamp = stamp;
    return list;
  }

  int _countWhere(bool Function(WalSyncDisplayState) test) => _allWals.where((w) => test(w.syncDisplayState)).length;

  int get syncingWalsCount => _countWhere((s) => s == WalSyncDisplayState.syncing);
  int get syncedWalsCount => _countWhere((s) => s == WalSyncDisplayState.synced);
  int get waitingWalsCount => _countWhere((s) => s == WalSyncDisplayState.waiting || s == WalSyncDisplayState.syncing);

  /// Recordings that need the user's attention: a sync failed (auto-retries
  /// exhausted) or the file is unreadable. Surfaced explicitly so a failure is
  /// never mistaken for a recording that simply hasn't synced yet.
  int get needsAttentionWalsCount =>
      _countWhere((s) => s == WalSyncDisplayState.failed || s == WalSyncDisplayState.corrupted);

  int get retryingWalsCount => _countWhere((s) => s == WalSyncDisplayState.retrying);

  /// Filtered + sorted list for the redesigned page's segmented filter.
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) {
    bool keep(Wal w) {
      switch (filter) {
        case WalDisplayFilter.all:
          return true;
        case WalDisplayFilter.pending:
          return w.status != WalStatus.corrupted && w.syncDisplayState != WalSyncDisplayState.synced;
        case WalDisplayFilter.synced:
          return w.syncDisplayState == WalSyncDisplayState.synced;
      }
    }

    return displaySortedWals.where(keep).toList();
  }

  List<Wal> get filteredWals {
    if (_storageFilter == null) {
      return _allWals;
    }

    // SD Card filter: show WALs on SD card OR transferred from SD card
    if (_storageFilter == WalStorage.sdcard) {
      return _allWals
          .where((wal) => wal.storage == WalStorage.sdcard || wal.originalStorage == WalStorage.sdcard)
          .toList();
    }

    // Flash Page filter: show WALs on flash page OR transferred from flash page
    if (_storageFilter == WalStorage.flashPage) {
      return _allWals
          .where((wal) => wal.storage == WalStorage.flashPage || wal.originalStorage == WalStorage.flashPage)
          .toList();
    }

    // Phone filter: show WALs on phone that are NOT originally from SD card or flash page
    if (_storageFilter == WalStorage.disk || _storageFilter == WalStorage.mem) {
      return _allWals
          .where(
            (wal) =>
                (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
                wal.originalStorage != WalStorage.sdcard &&
                wal.originalStorage != WalStorage.flashPage,
          )
          .toList();
    }

    // Other filters
    return _allWals.where((wal) => wal.storage == _storageFilter).toList();
  }

  // Sync state
  SyncState _syncState = const SyncState();
  SyncState get syncState => _syncState;

  // Track WAL processing progress
  int _totalWalsToProcess = 0;
  int _walsProcessedCount = 0;
  bool _isDisposed = false;
  late bool _freshRateLimitWasActive;
  late bool _backfillRateLimitWasActive;

  // Computed properties for backward compatibility
  List<Wal> get missingWals => _allWals.where((w) => w.status == WalStatus.miss).toList();
  int get missingWalsInSeconds =>
      missingWals.isEmpty ? 0 : missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

  /// Missing WALs that are still on device storage (SD card or Limitless flash page)
  /// These are files that need to be downloaded from the hardware device
  List<Wal> get missingWalsOnDevice => _allWals
      .where((w) => w.status == WalStatus.miss && (w.storage == WalStorage.sdcard || w.storage == WalStorage.flashPage))
      .toList();

  // Backward compatibility getters
  bool get isSyncing => _syncState.isSyncing;
  bool get syncCompleted => _syncState.isCompleted;
  bool get isFetchingConversations => _syncState.isFetchingConversations;
  double get walsSyncedProgress => _syncState.progress;
  double? get syncSpeedKBps => _syncState.speedKBps;
  List<SyncedConversationPointer> get syncedConversationsPointers {
    final sorted = List<SyncedConversationPointer>.from(_syncState.syncedConversations);
    sorted.sort((a, b) => (b.conversation.createdAt).compareTo(a.conversation.createdAt));
    return sorted;
  }

  String? get syncError => _syncState.errorMessage;
  Wal? get failedWal => _syncState.failedWal;
  SyncMethod? get currentSyncMethod => _syncState.syncMethod;

  // Flash page (Limitless) sync state
  bool get isFlashPageSyncing => _walService.getSyncs().isFlashPageSyncing;

  /// Get a WAL by ID from the current list
  Wal? getWalById(String walId) {
    try {
      return _allWals.firstWhere((w) => w.id == walId);
    } catch (e) {
      return null;
    }
  }

  // Audio playback delegates
  String? get currentPlayingWalId => _audioPlayerUtils.currentPlayingId;
  bool get isProcessingAudio => _audioPlayerUtils.isProcessingAudio;
  Duration get currentPosition => _audioPlayerUtils.currentPosition;
  Duration get totalDuration => _audioPlayerUtils.totalDuration;
  double get playbackProgress => _audioPlayerUtils.playbackProgress;

  IWalService get _walService => _walServiceOverride ?? ServiceManager.instance().wal;

  SyncProvider({
    IWalService? walService,
    SyncUploadGate? uploadGate,
    @visibleForTesting bool startBackgroundSync = true,
    @visibleForTesting Future<void> Function(LocalWalSyncImpl phone)? waitForWalReady,
    @visibleForTesting Future<void> Function()? startRecovery,
    @visibleForTesting Future<void> Function(WakeTrigger trigger)? wakeTransfer,
  }) : _walServiceOverride = walService,
       _uploadGate = uploadGate ?? SyncUploadGate.instance,
       _startBackgroundSync = startBackgroundSync,
       _waitForWalReady = waitForWalReady ?? ((phone) => phone.walReady),
       _startRecovery = startRecovery ?? (() => RecordingTransferCoordinator.instance.wake(WakeTrigger.startup)),
       _wakeTransfer = wakeTransfer ?? ((trigger) => RecordingTransferCoordinator.instance.wake(trigger)) {
    _walService.subscribe(this, this);
    _audioPlayerUtils.addListener(_onAudioPlayerStateChanged);
    _freshRateLimitWasActive = SyncRateLimiter.instance.isLimitedForLane('fresh');
    _backfillRateLimitWasActive = SyncRateLimiter.instance.isLimitedForLane('backfill');
    SyncRateLimiter.instance.addListener(_onRateLimiterChanged);
    initialized = _initializeProvider();
  }

  Future<void> _initializeProvider() async {
    try {
      await refreshWals();
      if (_isDisposed) return;
      await _uploadGate.reconcileFairUseStatus();
      if (_isDisposed) return;
      if (_startBackgroundSync) {
        await _attachTransferCoordinator();
      }
    } catch (error, stackTrace) {
      Logger.error('SyncProvider: initialization failed: $error\n$stackTrace');
    }
  }

  void _onRateLimiterChanged() {
    if (_isDisposed) return;
    final freshActive = SyncRateLimiter.instance.isLimitedForLane('fresh');
    final backfillActive = SyncRateLimiter.instance.isLimitedForLane('backfill');
    final cooldownEnded =
        (_freshRateLimitWasActive && !freshActive) || (_backfillRateLimitWasActive && !backfillActive);
    _freshRateLimitWasActive = freshActive;
    _backfillRateLimitWasActive = backfillActive;
    notifyListeners();
    if (cooldownEnded && _startBackgroundSync) {
      unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
    }
  }

  /// Wait for persisted WALs before attaching the single recovery owner, so
  /// its sole startup wake cannot race an empty in-memory inventory.
  Future<void> _attachTransferCoordinator() async {
    try {
      final phone = _walService.getSyncs().phone;
      await _waitForWalReady(phone);
      if (_isDisposed) return;
      SyncReconciler.instance.attach(phone, _onReconciledConversations);
      RecordingTransferCoordinator.instance.configure(
        reconcile: SyncReconciler.instance.poke,
        discover: _discoverPendingWals,
        refreshPending: refreshWals,
        drain: _drainEligibleWals,
        autoUploadEnabled: () =>
            !SharedPreferencesUtil().useCustomStt && SharedPreferencesUtil().autoSyncOfflineRecordings,
        connectivityChanges: ConnectivityService().onConnectionChange,
        initiallyConnected: ConnectivityService().isConnected,
      );
      unawaited(_startRecovery());
    } catch (e) {
      Logger.debug('SyncProvider: attach recording transfer coordinator failed: $e');
    }
  }

  /// Called by the reconciler when a background job finished and produced
  /// conversations. Surfaces them without disturbing an active sync.
  Future<void> _onReconciledConversations(SyncLocalFilesResponse result) async {
    if (_isDisposed) return;
    final conversations = await ConversationSyncUtils.processConversationIds(
      newConversationIds: result.newConversationIds,
      updatedConversationIds: result.updatedConversationIds,
    );
    if (_isDisposed) return;
    if (conversations.isNotEmpty && !_syncState.isProcessing) {
      // Append to whatever is already shown — jobs reconcile incrementally.
      final merged = [..._syncState.syncedConversations, ...conversations];
      _updateSyncState(_syncState.toCompleted(conversations: merged));
    }
    await refreshWals();
  }

  Future<void> _discoverPendingWals() async {
    if (_isDisposed) return;
    await _walService.getSyncs().refreshWalsFromDevice();
  }

  Future<RecordingTransferDrainResult> _drainEligibleWals() async {
    if (_isDisposed || _syncState.isProcessing) return const RecordingTransferDrainResult.contended();
    if (_walService.getSyncs().isStorageSyncing || _walService.getSyncs().isSdCardSyncing) {
      return const RecordingTransferDrainResult.contended();
    }

    final hadEligibleWals = missingWals.isNotEmpty;
    if (!hadEligibleWals) return const RecordingTransferDrainResult.skipped();

    _updateSyncState(_syncState.toIdle());
    _totalWalsToProcess = missingWals.length;
    _walsProcessedCount = 0;
    final result = await _performSync(
      operation: () => _walService.getSyncs().syncAll(progress: this),
      context: 'coordinated recording transfer',
      rethrowOnError: true,
    );
    await refreshWals();
    return RecordingTransferDrainResult(
      attempted: true,
      failed: (result?.localUploadFailures ?? 0) > 0,
      needsReconciliation: uploadedWals.isNotEmpty,
    );
  }

  void _onAudioPlayerStateChanged() {
    notifyListeners();
  }

  void _updateSyncState(SyncState newState) {
    _syncState = newState;
    notifyListeners();
  }

  Future<void> refreshWals() async {
    _isLoadingWals = true;
    notifyListeners();

    _allWals = await _walService.getSyncs().getAllWals();
    Logger.debug('SyncProvider: Loaded ${_allWals.length} WALs (${missingWals.length} missing)');

    _isLoadingWals = false;
    notifyListeners();
  }

  /// Enumerate offline recordings directly from the device, then refresh the
  /// list. Lets the Auto Sync page show device recordings (with a manual Sync
  /// option) even when auto-sync is turned off — device discovery otherwise only
  /// happens as the first step of a full sync. Best-effort: swallows BLE errors.
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {
    try {
      await _walService.getSyncs().refreshWalsFromDevice(firmwareVersion: firmwareVersion);
    } catch (e) {
      Logger.debug('SyncProvider: device WAL discovery failed: $e');
    }
    await refreshWals();
  }

  Future<WalStats> getWalStats() async {
    return await _walService.getSyncs().getWalStats();
  }

  Future<void> deleteWal(Wal wal) async {
    await _walService.getSyncs().deleteWal(wal);
    await refreshWals();
  }

  Future<void> deleteAllSyncedWals() async {
    await _walService.getSyncs().deleteAllSyncedWals();
    await refreshWals();
  }

  Future<void> deleteAllPendingWals() async {
    await _walService.getSyncs().deleteAllPendingWals();
    await refreshWals();
  }

  /// Clears every local recording category. Unlike the retryable Pending
  /// action, this deliberately includes terminally corrupted phone WALs.
  Future<void> deleteAllClearableWals() async {
    final syncs = _walService.getSyncs();
    await syncs.deleteAllSyncedWals();
    await syncs.deleteAllPendingWals();
    await syncs.deleteAllCorruptedWals();
    await refreshWals();
  }

  Future<void> syncWals({WakeTrigger trigger = WakeTrigger.userRetry}) async {
    if (_startBackgroundSync) {
      await _wakeTransfer(trigger);
      return;
    }
    await _syncWalsDirect();
  }

  Future<void> _syncWalsDirect() async {
    _updateSyncState(_syncState.toIdle());
    _totalWalsToProcess = missingWals.length;
    _walsProcessedCount = 0;
    await _performSync(
      operation: () => _walService.getSyncs().syncAll(progress: this),
      context: 'sync all WALs',
    );
  }

  Future<void> syncWal(Wal wal) async {
    // UI Sync/Auto Sync still call syncWal for a single row, but must not
    // race a coordinator drain (or device download) on the same WAL stack.
    if (_startBackgroundSync && _isTransferSeamBusy()) {
      await _wakeTransfer(WakeTrigger.userRetry);
      return;
    }
    _updateSyncState(_syncState.toIdle());
    final result = await _performSync(
      operation: () => _walService.getSyncs().syncWal(wal: wal, progress: this),
      context: 'sync WAL ${wal.id}',
      failedWal: wal,
    );
    // A 202 leaves the WAL `uploaded` — wake the single owner so reconcile
    // is scheduled (do not poke SyncReconciler here).
    if (result != null && _startBackgroundSync) {
      unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
    }
  }

  bool _isTransferSeamBusy() {
    if (_syncState.isProcessing) return true;
    final syncs = _walService.getSyncs();
    return syncs.isStorageSyncing == true || syncs.isSdCardSyncing == true;
  }

  Future<SyncLocalFilesResponse?> _performSync({
    required Future<SyncLocalFilesResponse?> Function() operation,
    required String context,
    Wal? failedWal,
    bool rethrowOnError = false,
  }) async {
    try {
      _updateSyncState(_syncState.toSyncing());

      // Check for SD card WALs - if present, log two-phase sync
      final sdCardWals = missingWals.where((w) => w.storage == WalStorage.sdcard).toList();
      if (sdCardWals.isNotEmpty) {
        Logger.debug('SyncProvider: Two-phase sync - ${sdCardWals.length} SD card files will be downloaded first');
      }

      DebugLogManager.logInfo('SyncProvider: starting $context', {
        'totalMissing': missingWals.length,
        'sdCardWals': sdCardWals.length,
        'deviceWals': missingWalsOnDevice.length,
      });

      final result = await operation();

      // If sync was cancelled while awaiting, don't override the cancel state.
      // cancelSync() already processed any partial conversation results.
      if (!_syncState.isSyncing && _syncState.status != SyncStatus.fetchingConversations) {
        return result;
      }

      // Process successful conversation IDs even when other batches failed —
      // localUploadFailures must not discard completed results.
      if (result != null && _hasConversationResults(result)) {
        Logger.debug(
          'SyncProvider: $context returned ${result.newConversationIds.length} new, ${result.updatedConversationIds.length} updated conversations',
        );
        DebugLogManager.logInfo('SyncProvider: $context succeeded', {
          'newConversations': result.newConversationIds.length,
          'updatedConversations': result.updatedConversationIds.length,
        });
        await _processConversationResults(result);
      } else if ((result?.localUploadFailures ?? 0) == 0) {
        DebugLogManager.logInfo('SyncProvider: $context completed with no new conversations');
        _updateSyncState(_syncState.toCompleted(conversations: []));
      }

      if ((result?.localUploadFailures ?? 0) > 0) {
        _updateSyncState(_syncState.toError(message: 'Upload failed. Check your connection and try again'));
      }
      return result;
    } catch (e) {
      final errorMessage = _formatSyncError(e, failedWal);
      Logger.debug('SyncProvider: Error in $context: $errorMessage');
      DebugLogManager.logError(e, null, 'SyncProvider: $context failed: $errorMessage', {
        if (failedWal != null) 'walId': failedWal.id,
        if (failedWal != null) 'walStorage': failedWal.storage.toString(),
      });
      _updateSyncState(_syncState.toError(message: errorMessage, failedWal: failedWal));
      if (rethrowOnError) rethrow;
      return null;
    }
  }

  bool _hasConversationResults(SyncLocalFilesResponse result) {
    return result.newConversationIds.isNotEmpty || result.updatedConversationIds.isNotEmpty;
  }

  String _formatSyncError(dynamic error, Wal? wal) {
    var baseMessage = error.toString().replaceAll('Exception: ', '');

    if (baseMessage.toLowerCase().contains('timeout')) {
      baseMessage = 'Device did not respond';
    } else if (baseMessage.toLowerCase().contains('could not be processed')) {
      baseMessage = 'Audio file could not be processed';
    } else if (baseMessage.toLowerCase().contains('too large')) {
      baseMessage = 'Recording is too large to upload';
    } else if (baseMessage.toLowerCase().contains('temporarily unavailable')) {
      baseMessage = 'Server is temporarily unavailable. Try again later';
    } else if (baseMessage.toLowerCase().contains('upload failed')) {
      baseMessage = 'Upload failed. Check your connection and try again';
    }

    if (wal != null) {
      final walInfo = '${secondsToHumanReadable(wal.seconds)} (${wal.codec.toFormattedString()})';
      final source = wal.storage == WalStorage.sdcard ? 'SD card' : 'phone';
      return 'Failed to process $source audio file $walInfo: $baseMessage';
    }

    return baseMessage;
  }

  Future<void> retrySync() async {
    if (_startBackgroundSync) {
      await _wakeTransfer(WakeTrigger.userRetry);
      return;
    }
    final failedWal = _syncState.failedWal;
    if (failedWal != null) {
      await syncWal(failedWal);
    } else {
      await _syncWalsDirect();
    }
  }

  void clearSyncResult() {
    _updateSyncState(_syncState.toIdle());
  }

  void setStorageFilter(WalStorage? filter) {
    _storageFilter = filter;
    notifyListeners();
  }

  void clearStorageFilter() {
    _storageFilter = null;
    notifyListeners();
  }

  Future<void> _processConversationResults(SyncLocalFilesResponse result) async {
    _updateSyncState(_syncState.toFetchingConversations());
    final conversations = await ConversationSyncUtils.processConversationIds(
      newConversationIds: result.newConversationIds,
      updatedConversationIds: result.updatedConversationIds,
    );
    _updateSyncState(_syncState.toCompleted(conversations: conversations));
    // Refresh WAL list so home screen cloud icon updates (clears synced WALs)
    await refreshWals();
  }

  // Audio playback delegate methods
  bool isWalPlaying(String walId) => _audioPlayerUtils.isPlaying(walId);
  bool canPlayOrShareWal(Wal wal) => _audioPlayerUtils.canPlayOrShare(wal);

  Future<void> toggleWalPlayback(Wal wal) async {
    await _audioPlayerUtils.togglePlayback(wal);
  }

  Future<void> shareWalAsWav(Wal wal) async {
    await _audioPlayerUtils.shareAsAudio(wal);
  }

  Future<void> seekToPosition(Duration position) async {
    await _audioPlayerUtils.seekToPosition(position);
  }

  Future<void> skipForward({Duration duration = const Duration(seconds: 10)}) async {
    await _audioPlayerUtils.skipForward(duration: duration);
  }

  Future<void> skipBackward({Duration duration = const Duration(seconds: 10)}) async {
    await _audioPlayerUtils.skipBackward(duration: duration);
  }

  Future<List<double>?> getWaveformForWal(String walId) async {
    final wal = _allWals.firstWhere((w) => w.id == walId, orElse: () => throw Exception('WAL not found'));

    String? wavFilePath = _audioPlayerUtils.getCachedAudioPath(walId);
    if (wavFilePath == null && canPlayOrShareWal(wal)) {
      wavFilePath = await _audioPlayerUtils.ensureAudioFileExists(wal);
    }

    return await compute(_generateWaveformInBackground, {'walId': walId, 'wavFilePath': wavFilePath});
  }

  static Future<List<double>?> _generateWaveformInBackground(Map<String, dynamic> params) async {
    final String walId = params['walId'];
    final String? wavFilePath = params['wavFilePath'];

    return await WaveformUtils.generateWaveform(walId, wavFilePath);
  }

  @override
  void onWalUpdated() async {
    await refreshWals();
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) async {
    await refreshWals();

    // Update progress based on WALs synced if we're currently syncing
    if (_syncState.isSyncing) {
      _walsProcessedCount++;
      // If device download created new WALs, total grows dynamically
      final currentMissing = _allWals.where((w) => w.status == WalStatus.miss).length;
      final newTotal = _walsProcessedCount + currentMissing;
      if (newTotal > _totalWalsToProcess) {
        _totalWalsToProcess = newTotal;
      }
      final walProgress = walBasedProgress;
      _updateSyncState(_syncState.toSyncing(progress: walProgress));
    }
  }

  @override
  void onStatusChanged(WalServiceStatus status) {
    Logger.debug('SyncProvider: WAL service status changed to $status');
  }

  @override
  void onWalSyncedProgress(
    double percentage, {
    double? speedKBps,
    SyncPhase? phase,
    int? currentFile,
    int? totalFiles,
    int? uploadedBytes,
    int? totalBytesToUpload,
  }) {
    if (_syncState.isSyncing) {
      _updateSyncState(
        _syncState.toSyncing(
          progress: percentage,
          speedKBps: speedKBps,
          phase: phase,
          currentFile: currentFile,
          totalFiles: totalFiles,
          uploadedBytes: uploadedBytes,
          totalBytesToUpload: totalBytesToUpload,
        ),
      );
    }
  }

  /// Cancel ongoing sync operation.
  /// If batches already completed, immediately shows their conversation results.
  void cancelSync() {
    DebugLogManager.logWarning('SyncProvider: user cancelled sync');
    // Grab accumulated results before cancelling
    final partialResults = _walService.getSyncs().accumulatedResponse;
    _walService.getSyncs().cancelSync();
    // Immediately clear isSyncing on all loaded WALs so UI updates right away
    for (final wal in _allWals) {
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
    }
    // If batches already completed with conversations, show them immediately
    if (partialResults != null && _hasConversationResults(partialResults)) {
      _processConversationResults(partialResults);
    } else {
      _updateSyncState(_syncState.toIdle());
    }
    // Cancel only stops further uploads. Recordings already `uploaded` are
    // safe on the server — keep reconciling them through the single owner.
    unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
  }

  /// Transfer a single WAL from device storage (SD card or flash page) to phone storage
  Future<void> transferWalToPhone(Wal wal) async {
    if (wal.storage != WalStorage.sdcard && wal.storage != WalStorage.flashPage) {
      throw Exception('This recording is already on phone');
    }

    _updateSyncState(_syncState.toSyncing());

    try {
      await _walService.getSyncs().syncWal(wal: wal, progress: this);
      await refreshWals();
      _updateSyncState(_syncState.toIdle());
    } catch (e) {
      await refreshWals();
      _updateSyncState(_syncState.toIdle());
      rethrow;
    }
  }

  /// Check if SD card sync is in progress
  bool get isSdCardSyncing => _walService.getSyncs().isSdCardSyncing;

  // Calculate progress based on WALs synced
  double get walBasedProgress {
    if (_totalWalsToProcess == 0) return 0.0;
    return (_walsProcessedCount / _totalWalsToProcess).clamp(0.0, 1.0);
  }

  // Get the number of WALs processed
  int get processedWalsCount => _walsProcessedCount;

  // Get the total WALs to process
  int get initialMissingWalsCount => _totalWalsToProcess;

  @override
  void dispose() {
    _isDisposed = true;
    _audioPlayerUtils.removeListener(_onAudioPlayerStateChanged);
    SyncRateLimiter.instance.removeListener(_onRateLimiterChanged);
    WaveformUtils.clearCache();
    _walService.unsubscribe(this);
    super.dispose();
  }
}
