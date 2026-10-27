import 'dart:async';

import 'package:omi/services/wals/periodic_recording_sync.dart';

import 'package:flutter/foundation.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/conversation_sync_utils.dart';
import 'package:omi/utils/sync/offline_processing_display.dart';
import 'package:omi/utils/waveform_utils.dart';

enum WalStatusFilter { pending, synced, corrupted }

enum WalDisplayFilter { all, pending, synced }

List<SyncedConversationPointer> sortSyncedConversationPointers(Iterable<SyncedConversationPointer> pointers) {
  final sorted = List<SyncedConversationPointer>.from(pointers);
  sorted.sort((a, b) {
    final aDate = a.conversation.startedAt ?? a.conversation.createdAt;
    final bDate = b.conversation.startedAt ?? b.conversation.createdAt;
    return bDate.compareTo(aDate);
  });
  return sorted;
}

class SyncProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  /// Machine-readable error state consumed by sync surfaces, which own the
  /// localized copy. Providers must not embed user-facing English in state.
  static const pendingUploadErrorCode = 'sync_pending_upload';

  static bool isPendingUploadError(String? message) => message == pendingUploadErrorCode;

  // Services
  final AudioPlayerUtils _audioPlayerUtils = AudioPlayerUtils.instance;
  final IWalService? _walServiceOverride;
  final SyncUploadGate _uploadGate;
  final bool _startBackgroundSync;
  final Future<void> Function(LocalWalSyncImpl phone) _waitForWalReady;
  final Future<void> Function() _startRecovery;
  final Future<void> Function(WakeTrigger trigger) _wakeTransfer;
  final SyncTransferKeepAlive _keepAlive;
  PeriodicRecordingSync? _periodicSync;
  final CaptureWedgeMonitor _captureWedgeMonitor;

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
  List<Wal>? _sortedSource;
  List<(Wal, int)>? _sortedInput;

  // Transfer callbacks can arrive once per flash page/chunk. Keep the state
  // current, but bound background inventory reads and scalar UI publications.
  static const _uiPublishInterval = Duration(milliseconds: 100);
  Timer? _walUpdateTimer;
  Future<void>? _walUpdateRefresh;
  bool _walUpdatePending = false;
  Timer? _progressNotifyTimer;

  @override
  void notifyListeners() {
    // Any publication already delivers the latest progress; a queued progress
    // callback would only publish the same state again.
    _progressNotifyTimer?.cancel();
    _progressNotifyTimer = null;
    super.notifyListeners();
  }

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
      w.status != WalStatus.corrupted &&
      w.status != WalStatus.uploadRejected &&
      (w.status == WalStatus.miss || w.status == WalStatus.uploaded || w.isSyncing);

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
      } else if (w.status == WalStatus.corrupted ||
          w.status == WalStatus.outsideRecoveryWindow ||
          w.status == WalStatus.unsupportedAudio ||
          w.status == WalStatus.uploadRejected) {
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

  /// Recordings excluded from automatic uploads. Request refusals can be
  /// explicitly re-armed; confirmed audio/window failures stay terminal.
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
  /// A refresh returns a new list even when only mutable progress/status fields
  /// changed. Validate membership and captured sort keys once per new inventory
  /// instead of re-sorting history on every chunk. Capturing timerStart also
  /// detects the device replacing an estimated timestamp in place.
  List<Wal> get displaySortedWals {
    final cached = _sortedCache;
    final previous = _sortedInput;
    if (cached != null && previous != null && previous.length == _allWals.length) {
      if (identical(_sortedSource, _allWals)) return cached;
      var unchanged = true;
      for (var i = 0; i < _allWals.length; i++) {
        final wal = _allWals[i];
        if (!identical(previous[i].$1, wal) || previous[i].$2 != wal.timerStart) {
          unchanged = false;
          break;
        }
      }
      if (unchanged) {
        _sortedSource = _allWals;
        return cached;
      }
    }
    _sortedSource = _allWals;
    _sortedInput = [for (final wal in _allWals) (wal, wal.timerStart)];
    final list = List<Wal>.from(_allWals);
    list.sort((a, b) => b.timerStart.compareTo(a.timerStart));
    _sortedCache = list;
    return list;
  }

  int _countWhere(bool Function(WalSyncDisplayState) test) => _allWals.where((w) => test(w.syncDisplayState)).length;

  int get syncingWalsCount => _countWhere((s) => s == WalSyncDisplayState.syncing);
  int get syncedWalsCount => _countWhere((s) => s == WalSyncDisplayState.synced);
  int get waitingWalsCount => _countWhere((s) => s == WalSyncDisplayState.waiting || s == WalSyncDisplayState.syncing);

  /// Recordings that need the user's attention: a sync failed (auto-retries
  /// exhausted), the file is unreadable, or the server permanently refused it
  /// for being too old. Surfaced explicitly so a failure is never mistaken for
  /// a recording that simply hasn't synced yet.
  int get needsAttentionWalsCount => _countWhere(
        (s) =>
            s == WalSyncDisplayState.failed ||
            s == WalSyncDisplayState.corrupted ||
            s == WalSyncDisplayState.outsideRecoveryWindow ||
            s == WalSyncDisplayState.unsupportedAudio ||
            s == WalSyncDisplayState.uploadRejected,
      );

  /// Spent retry budgets and request refusals can be explicitly retried.
  /// Missing files, permanent audio/lookback verdicts and the deterministic
  /// too-large refusal remain excluded.
  List<Wal> get retryableAttentionWals => _allWals.where(walRetryCanHelp).toList();

  /// Retry every recording in [retryableAttentionWals]. The automatic drain
  /// skips a recording once its budget is spent, so a plain [syncWals] from
  /// the Needs Attention card left every one of them where it was; grant the
  /// fresh budget a per-recording Retry gives ([syncWal]) before draining.
  Future<void> retryNeedsAttentionWals() async {
    for (final wal in retryableAttentionWals) {
      wal.prepareManualRetry();
    }
    await syncWals();
  }

  /// Durable HTTP refusals that automatic connectivity wakes must never retry.
  /// The Auto Sync Needs Attention chip renders this count through
  /// [needsAttentionWalsCount]; this narrower accessor keeps the terminal-HTTP
  /// incident observable in tests and diagnostics.
  int get terminallyFailedWalsCount => _allWals.where((w) => w.status == WalStatus.uploadRejected).length;

  int get retryingWalsCount => _countWhere((s) => s == WalSyncDisplayState.retrying);

  /// Filtered + sorted list for the redesigned page's segmented filter.
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) {
    bool keep(Wal w) {
      switch (filter) {
        case WalDisplayFilter.all:
          return true;
        case WalDisplayFilter.pending:
          return w.status != WalStatus.corrupted &&
              w.status != WalStatus.outsideRecoveryWindow &&
              w.status != WalStatus.unsupportedAudio &&
              w.status != WalStatus.uploadRejected &&
              w.syncDisplayState != WalSyncDisplayState.synced;
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
  Set<String> _uploadedWalIdsAtSyncStart = const {};
  final Set<String> _trackedServerJobWalIds = {};
  bool _isDisposed = false;
  late bool _rateLimitWasActive;

  /// Bumped on [clearUserData]. Capture at admission; never re-read after an
  /// await. Adopting the live counter would publish stale work into the session
  /// that replaced it.
  int _sessionGeneration = 0;

  /// Generation of in-flight sync/drain/reconcile. Coordinator callbacks must
  /// use this token, not `_sessionGeneration` at callback time. -1 means no
  /// admitted work. Cleared only by [clearUserData] / dispose, not by adopting
  /// a newer session.
  int _admittedWorkGeneration = -1;

  // Computed properties for backward compatibility
  List<Wal> get missingWals => _allWals.where((w) => w.status == WalStatus.miss).toList();
  int get missingWalsInSeconds =>
      missingWals.isEmpty ? 0 : missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

  /// Missing WALs that are still on device storage (SD card or Limitless flash page)
  /// These are files that need to be downloaded from the hardware device
  List<Wal> get missingWalsOnDevice => _allWals
      .where((w) => w.status == WalStatus.miss && (w.storage == WalStorage.sdcard || w.storage == WalStorage.flashPage))
      .toList();

  /// Phone-local recordings still waiting to be uploaded for transcription —
  /// the backlog a transcription outage or offline capture leaves behind.
  /// Uploads that already reached the server (`uploaded`, processing there)
  /// count too: their transcripts are still pending. Device-side files are
  /// [missingWalsOnDevice], a different drain.
  List<Wal> get pendingLocalTranscriptionWals => pendingWals.where((w) => w.storage == WalStorage.disk).toList();

  // Backward compatibility getters
  bool get isSyncing => _syncState.isSyncing;
  bool get syncCompleted => _syncState.isCompleted;
  bool get isFetchingConversations => _syncState.isFetchingConversations;
  double get walsSyncedProgress => _syncState.progress;
  double? get syncSpeedKBps => _syncState.speedKBps;
  List<SyncedConversationPointer> get syncedConversationsPointers {
    return sortSyncedConversationPointers(_syncState.syncedConversations);
  }

  String? get syncError => _syncState.errorMessage;
  Wal? get failedWal => _syncState.failedWal;
  SyncMethod? get currentSyncMethod => _syncState.syncMethod;

  // Flash page (Limitless) sync state
  bool get isFlashPageSyncing => _walService.getSyncs().isFlashPageSyncing;

  /// Applies the auto-remove synced-copies retention preference immediately
  /// (called when the user enables the toggle). Best-effort; failures are
  /// swallowed — the sweep re-runs on the next sync pass regardless.
  Future<void> applySyncedCopyRetention() async {
    try {
      await _walService.getSyncs().phone.applySyncedCopyRetention();
    } catch (_) {}
  }

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
    @visibleForTesting SyncTransferKeepAlive? keepAlive,
    @visibleForTesting CaptureWedgeMonitor? captureWedgeMonitor,
  })  : _walServiceOverride = walService,
        _uploadGate = uploadGate ?? SyncUploadGate.instance,
        _startBackgroundSync = startBackgroundSync,
        _waitForWalReady = waitForWalReady ?? ((phone) => phone.walReady),
        _startRecovery = startRecovery ?? (() => RecordingTransferCoordinator.instance.wake(WakeTrigger.startup)),
        _wakeTransfer = wakeTransfer ?? ((trigger) => RecordingTransferCoordinator.instance.wake(trigger)),
        _keepAlive = keepAlive ?? SyncTransferKeepAlive.instance,
        _captureWedgeMonitor = captureWedgeMonitor ?? CaptureWedgeMonitor.instance {
    _walService.subscribe(this, this);
    _audioPlayerUtils.addListener(_onAudioPlayerStateChanged);
    _rateLimitWasActive = SyncRateLimiter.instance.isLimited;
    SyncRateLimiter.instance.addListener(_onRateLimiterChanged);
    initialized = _initializeProvider();
  }

  bool _isCurrent(int generation) => !_isDisposed && generation >= 0 && generation == _sessionGeneration;

  /// Wipes published sync state and invalidates in-flight work. Durable WAL
  /// writes already issued stay bound to the account that admitted them; their
  /// completion must not publish into the next session.
  void clearUserData() {
    _cancelQueuedWalUpdates();
    _walUpdateRefresh = null;
    _sessionGeneration++;
    _admittedWorkGeneration = -1;
    _walService.getSyncs().clearUserData();
    // The capture monitor singleton outlives the provider: without this, the
    // previous account's unseen flag and storage/upload counts light the bell
    // for the next login.
    _captureWedgeMonitor.reset();
    _allWals = [];
    _isLoadingWals = false;
    _syncState = const SyncState();
    _trackedServerJobWalIds.clear();
    _uploadedWalIdsAtSyncStart = {};
    _sortedCache = null;
    _sortedSource = null;
    _sortedInput = null;
    _pendingWalsCache = null;
    _syncedWalsCache = null;
    _corruptedWalsCache = null;
    _filteredWalsCacheStamp = 0;
    _totalWalsToProcess = 0;
    _walsProcessedCount = 0;
    notifyListeners();
  }

  Future<void> _initializeProvider() async {
    final generation = _sessionGeneration;
    try {
      await _refreshWals(generation);
      if (!_isCurrent(generation)) return;
      await _uploadGate.reconcileFairUseStatus();
      if (!_isCurrent(generation)) return;
      if (_startBackgroundSync) {
        await _attachTransferCoordinator(generation);
      }
    } catch (error, stackTrace) {
      Logger.error('SyncProvider: initialization failed: $error\n$stackTrace');
    }
  }

  void _onRateLimiterChanged() {
    if (_isDisposed) return;
    final active = SyncRateLimiter.instance.isLimited;
    final cooldownEnded = _rateLimitWasActive && !active;
    _rateLimitWasActive = active;
    notifyListeners();
    if (cooldownEnded && _startBackgroundSync) {
      unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
    }
  }

  /// Wait for persisted WALs before attaching the single recovery owner, so
  /// its sole startup wake cannot race an empty in-memory inventory.
  Future<void> _attachTransferCoordinator(int generation) async {
    try {
      final phone = _walService.getSyncs().phone;
      await _waitForWalReady(phone);
      if (!_isCurrent(generation)) return;
      RecordingTransferCoordinator.instance.configure(
        reconcile: _reconcileAdmittedWals,
        discover: _discoverPendingWals,
        refreshPending: () => _refreshWals(_admittedWorkGeneration),
        drain: _drainEligibleWals,
        drainLiveCapture: _drainLiveCaptureWals,
        autoUploadEnabled: () =>
            !SharedPreferencesUtil().useCustomStt && SharedPreferencesUtil().autoSyncOfflineRecordings,
        connectivityChanges: ConnectivityService().onConnectionChange,
        initiallyConnected: ConnectivityService().isConnected,
        onTransferAdmitted: () => _admittedWorkGeneration = _isDisposed ? -1 : _sessionGeneration,
        onTransferStarted: _keepAlive.acquire,
        onTransferFinished: _keepAlive.release,
        onConnectivityRestored: () async {
          if (_isCurrent(_admittedWorkGeneration)) await phone.resetExhaustedAutoRetries();
        },
        networkChanges: ConnectivityService().onNetworkChange,
        hasPendingWork: () => pendingWals.any((wal) => !wal.holdForUser) || uploadedWals.isNotEmpty,
        onPassTimedOut: _onTransferPassTimedOut,
      );
      _periodicSync?.dispose();
      _periodicSync = PeriodicRecordingSync(
        coordinator: RecordingTransferCoordinator.instance,
        cancel: () => _walService.getSyncs().cancelSync(),
      );
      unawaited(_periodicSync!.start());
      unawaited(_startRecovery());
    } catch (e) {
      Logger.debug('SyncProvider: attach recording transfer coordinator failed: $e');
    }
  }

  /// The abandoned pass may still hold a BLE storage read or an upload; cancel
  /// it so the next pass does not contend with it.
  void _onTransferPassTimedOut(WakeTrigger trigger, Duration limit) {
    if (!_isCurrent(_admittedWorkGeneration)) return;
    _walService.getSyncs().cancelSync();
    unawaited(DebugLogManager.logWarning('transfer_pass_stuck', {'trigger': trigger.name, 'limit_s': limit.inSeconds}));
    const TypedEvents().emit(CaptureRecoveryObserved(
      kind: CaptureRecoveryObservedKind.transferPassTimedOut,
      trigger: trigger == WakeTrigger.periodic
          ? CaptureRecoveryObservedTrigger.periodic
          : CaptureRecoveryObservedTrigger.other,
    ));
  }

  Future<void> _reconcileAdmittedWals() async {
    final generation = _admittedWorkGeneration;
    if (!_isCurrent(generation)) return;
    SyncReconciler.instance.attach(
      _walService.getSyncs().phone,
      (result) => _onReconciledConversations(result, generation),
    );
    await SyncReconciler.instance.poke();
  }

  /// Called by the reconciler when a background job finished and produced
  /// conversations. Surfaces them without disturbing an active sync.
  Future<void> _onReconciledConversations(SyncLocalFilesResponse result, int generation) async {
    if (!_isCurrent(generation)) return;
    final refreshedIds = <String>{};
    final conversations = await ConversationSyncUtils.processConversationIds(
      newConversationIds: result.newConversationIds,
      updatedConversationIds: {
        ...result.updatedConversationIds,
        ..._syncState.syncedConversations.map((p) => p.conversation.id),
      }.toList(),
      onConversation: (id, _) {
        if (_isCurrent(generation)) refreshedIds.add(id);
      },
    );
    if (!_isCurrent(generation)) return;
    // Refresh WALs *before* updating the "synced" conversation UI so we don't
    // label recordings as synced while the reconciler is still leaving some
    // WALs in an uploaded/pending state (issue #7240).
    await _refreshWals(generation);
    if (!_isCurrent(generation)) return;
    if ((conversations.isNotEmpty || refreshedIds.isNotEmpty) && !_syncState.isProcessing) {
      // Append to whatever is already shown — jobs reconcile incrementally.
      final merged = [
        ..._syncState.syncedConversations.where((p) => !refreshedIds.contains(p.conversation.id)),
        ...conversations,
      ];
      final filtered = filterFullySyncedConversations(conversations: merged, wals: _allWals);
      _updateSyncState(_syncState.toCompleted(conversations: filtered), generation);
    }
  }

  Future<void> _discoverPendingWals() async {
    final generation = _admittedWorkGeneration;
    if (!_isCurrent(generation)) return;
    await _walService.getSyncs().refreshWalsFromDevice();
  }

  Future<RecordingTransferDrainResult> _drainEligibleWals() async {
    return _drainWals(liveCaptureOnly: false);
  }

  Future<RecordingTransferDrainResult> _drainLiveCaptureWals() async {
    return _drainWals(liveCaptureOnly: true);
  }

  Future<RecordingTransferDrainResult> _drainWals({required bool liveCaptureOnly}) async {
    final generation = _admittedWorkGeneration;
    if (!_isCurrent(generation) || _syncState.isProcessing) {
      return const RecordingTransferDrainResult.contended();
    }
    if (_walService.getSyncs().isStorageSyncing || _walService.getSyncs().isSdCardSyncing) {
      return const RecordingTransferDrainResult.contended();
    }

    final nowSeconds = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final eligibleWals = missingWals
        .where((wal) => !wal.holdForUser && (!liveCaptureOnly || isLiveCaptureWal(wal, nowSeconds)))
        .toList();
    final hadEligibleWals = eligibleWals.isNotEmpty;
    if (!hadEligibleWals) return const RecordingTransferDrainResult.skipped();

    // Reconciles a persisted fair-use cooldown the server may already have
    // lifted; without it a stale local deadline outlives the restriction.
    // Deliberately does not gate the drain: pulling audio off the device
    // consumes no upload quota, and the upload phases carry their own guard.
    await _uploadGate.prepareToUpload();
    if (!_isCurrent(generation)) return const RecordingTransferDrainResult.contended();

    _admittedWorkGeneration = generation;
    _updateSyncState(_syncState.toIdle(), generation);
    _totalWalsToProcess = eligibleWals.length;
    _walsProcessedCount = 0;
    final result = await _performSync(
      operation: () => liveCaptureOnly
          ? _walService.getSyncs().syncLiveCaptureOnly(progress: this)
          : _walService.getSyncs().syncAll(progress: this),
      context: liveCaptureOnly ? 'background live-capture transfer' : 'coordinated recording transfer',
      rethrowOnError: true,
      generation: generation,
    );
    await _refreshWals(generation);
    if (!_isCurrent(generation)) return const RecordingTransferDrainResult.contended();
    return RecordingTransferDrainResult(
      attempted: true,
      failed: (result?.localUploadFailures ?? 0) > 0,
      needsReconciliation: uploadedWals.isNotEmpty,
    );
  }

  void _onAudioPlayerStateChanged() {
    notifyListeners();
  }

  void _updateSyncState(SyncState newState, [int? generation]) {
    if (generation != null && !_isCurrent(generation)) return;
    _syncState = newState;
    notifyListeners();
  }

  Future<void> refreshWals() => _refreshWals(_sessionGeneration);

  /// Upload-stall attention's slice of the inventory: a phone-local, cloud-
  /// draining WAL that is still moving toward an upload. Mirrors
  /// [SyncPendingWork.isPendingWal] (which lives behind a page import and
  /// cannot be imported here without a cycle): local-only on-device-STT WALs
  /// never join a drain, and a WAL that already exhausted its retries is
  /// Offline Sync's terminal attention, not an upload stall — unless it is
  /// mid-sync right now, which is forward movement by definition.
  static bool _isUploadStallCandidate(Wal wal) =>
      wal.storage == WalStorage.disk &&
      !wal.onDeviceOnly &&
      !wal.holdForUser &&
      wal.status == WalStatus.miss &&
      (wal.isSyncing || wal.retryCount < walMaxAutoRetries);

  Future<void> _refreshWals(int generation) async {
    if (!_isCurrent(generation)) return;
    // Explicit refreshes and terminal callbacks take a fresh snapshot now and
    // supersede any queued background read.
    _cancelQueuedWalUpdates();
    _isLoadingWals = true;
    notifyListeners();

    final wals = await _walService.getSyncs().getAllWals();
    if (!_isCurrent(generation)) return;
    _allWals = wals;
    Logger.debug('SyncProvider: Loaded ${_allWals.length} WALs (${missingWals.length} missing)');
    // Upload-stall attention counts recordings, not WAL fragments: capture
    // writes ~1-minute fragments and other UI paths collapse them with
    // [groupRecordingBlocks]. Local-only WALs (on-device STT) never join a
    // cloud drain — counting them would light a stall that no upload can
    // clear — and only forward-moving (upload-eligible) work proves a stall.
    // Ordered by [displaySortedWals] — the memoized newest-first inventory —
    // so a refresh shares one sort with every other consumer instead of
    // re-sorting the index on the UI isolate (the same keyed order the
    // pending-work row reads).
    final uploadEligible = displaySortedWals.where(_isUploadStallCandidate).toList(growable: false);
    DateTime? oldestPendingAt;
    if (uploadEligible.isNotEmpty) {
      final oldestSeconds = uploadEligible.map((wal) => wal.timerStart).reduce((a, b) => a < b ? a : b);
      oldestPendingAt = DateTime.fromMillisecondsSinceEpoch(oldestSeconds * 1000);
    }
    // Fragment durations still sum across the same upload-eligible set: the
    // row reports the kept audio this stall holds, and a fragment that
    // already uploaded contributes none of its length to what waits.
    // Retry-exhausted WALs are Offline Sync's terminal attention — hours of
    // them must not read as audio waiting on this upload.
    final pendingSeconds = uploadEligible.fold<int>(0, (sum, wal) => sum + (wal.seconds > 0 ? wal.seconds : 0));
    _captureWedgeMonitor.observeWalBacklog(
      pendingCount: groupRecordingBlocks(uploadEligible).length,
      oldestPendingAt: oldestPendingAt,
      pendingSeconds: pendingSeconds,
    );
    try {
      final risk = _walService.getSyncs().phone.retentionRisk as WalRetentionRisk?;
      if (risk != null) {
        _captureWedgeMonitor.observeStorageAtRisk(
          engagedAt: risk.engagedAt,
          blockedCount: risk.blockedCount,
          retainedCount: risk.retainedCount,
          reason: risk.reason,
        );
      } else {
        // No retention risk reading: the disk admitted a write (or the older
        // alternate implementations expose no diagnostic), so the storage row
        // ends with its own condition instead of lingering forever.
        _captureWedgeMonitor.clearStorageAtRisk();
      }
    } catch (_) {
      // Test doubles and older alternate WAL implementations need not expose
      // the phone-local retention diagnostic.
    }

    _isLoadingWals = false;
    _publishSyncedCompletions(generation);
    notifyListeners();
  }

  /// Post-refresh publication for sync completions, once per coalesced refresh
  /// instead of once per finished WAL. Every producer of [onWalSynced] follows
  /// it with [onWalUpdated] in the same operation, so the trailing refresh
  /// always sees the burst's final state.
  void _publishSyncedCompletions(int generation) {
    if (!_isCurrent(generation)) return;
    // Keep finished recordings in the batch until all of it is done. Removing
    // each one as it finished shrank the total while "processed" stayed at
    // zero, so the card read "Processing 0/5914 · 0%" for the whole drain.
    if (_trackedServerJobWalIds.isNotEmpty &&
        !_allWals.any((w) => w.status == WalStatus.uploaded && _trackedServerJobWalIds.contains(w.id))) {
      _trackedServerJobWalIds.clear();
    }
    if (_totalWalsToProcess > 0) {
      // If device download created new WALs, total grows dynamically
      final currentMissing = _allWals.where((w) => w.status == WalStatus.miss).length;
      final newTotal = _walsProcessedCount + currentMissing;
      if (newTotal > _totalWalsToProcess) {
        _totalWalsToProcess = newTotal;
      }
    }
    if (_syncState.isSyncing) {
      _updateSyncState(_syncState.toSyncing(progress: walBasedProgress), generation);
    } else if (_totalWalsToProcess > 0 && uploadedWals.isNotEmpty) {
      notifyListeners();
    }
  }

  /// Enumerate offline recordings directly from the device, then refresh the
  /// list. Lets the Auto Sync page show device recordings (with a manual Sync
  /// option) even when auto-sync is turned off — device discovery otherwise only
  /// happens as the first step of a full sync. Best-effort: swallows BLE errors.
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {
    final generation = _sessionGeneration;
    try {
      await _walService.getSyncs().refreshWalsFromDevice(firmwareVersion: firmwareVersion);
    } catch (e) {
      Logger.debug('SyncProvider: device WAL discovery failed: $e');
    }
    await _refreshWals(generation);
  }

  Future<WalStats> getWalStats() async {
    return await _walService.getSyncs().getWalStats();
  }

  Future<void> deleteWal(Wal wal) async {
    final generation = _sessionGeneration;
    await _walService.getSyncs().deleteWal(wal);
    await _refreshWals(generation);
  }

  Future<void> deleteAllSyncedWals() async {
    final generation = _sessionGeneration;
    await _walService.getSyncs().deleteAllSyncedWals();
    await _refreshWals(generation);
  }

  Future<void> deleteAllPendingWals() async {
    final generation = _sessionGeneration;
    await _walService.getSyncs().deleteAllPendingWals();
    await _refreshWals(generation);
  }

  /// Clears every local recording category. Unlike the retryable Pending
  /// action, this deliberately includes terminally corrupted phone WALs.
  Future<void> deleteAllClearableWals() async {
    final generation = _sessionGeneration;
    final syncs = _walService.getSyncs();
    await syncs.deleteAllSyncedWals();
    await syncs.deleteAllPendingWals();
    await syncs.deleteAllCorruptedWals();
    await _refreshWals(generation);
  }

  Future<void> syncWals({WakeTrigger trigger = WakeTrigger.userRetry}) async {
    final generation = _sessionGeneration;
    if (_startBackgroundSync) {
      await _wakeTransfer(trigger);
      return;
    }
    await _syncWalsDirect(generation);
  }

  Future<void> _syncWalsDirect(int generation) async {
    await _uploadGate.prepareToUpload();
    if (!_isCurrent(generation)) return;
    _admittedWorkGeneration = generation;
    _updateSyncState(_syncState.toIdle(), generation);
    _totalWalsToProcess = missingWals.length;
    _walsProcessedCount = 0;
    await _performSync(
      operation: () => _walService.getSyncs().syncAll(progress: this),
      context: 'sync all WALs',
      checkFlashStall: true,
      generation: generation,
    );
  }

  Future<void> syncWal(Wal wal) async {
    final generation = _sessionGeneration;
    wal.prepareManualRetry();
    // UI Sync/Auto Sync still call syncWal for a single row, but must not
    // race a coordinator drain (or device download) on the same WAL stack.
    if (_startBackgroundSync && _isTransferSeamBusy()) {
      // Coalescing this tap into the running drain must not silently drop it:
      // the drain skips recordings whose auto-upload budget is spent, so grant
      // the same fresh budget the direct path gives.
      await _wakeTransfer(WakeTrigger.userRetry);
      return;
    }
    await _uploadGate.prepareToUpload();
    if (!_isCurrent(generation)) return;
    _admittedWorkGeneration = generation;
    _updateSyncState(_syncState.toIdle(), generation);
    _totalWalsToProcess = 1;
    _walsProcessedCount = 0;
    final result = await _performSync(
      operation: () => _walService.getSyncs().syncWal(wal: wal, progress: this),
      context: 'sync WAL ${wal.id}',
      failedWal: wal,
      checkFlashStall: wal.storage == WalStorage.flashPage,
      generation: generation,
    );
    if (!_isCurrent(generation)) return;
    // A 202 leaves the WAL `uploaded` — wake the single owner so reconcile
    // is scheduled (do not poke SyncReconciler here). Soft-retry failures wake
    // from _performSync itself; do not double-wake here.
    if (result != null &&
        result.localUploadFailures == 0 &&
        result.localUploadPermanentFailures == 0 &&
        _startBackgroundSync) {
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
    required int generation,
    Wal? failedWal,
    bool rethrowOnError = false,
    bool checkFlashStall = false,
  }) async {
    if (!_isCurrent(generation)) return null;
    _admittedWorkGeneration = generation;
    _uploadedWalIdsAtSyncStart = uploadedWals.map((w) => w.id).toSet();
    await _keepAlive.acquire();
    try {
      _updateSyncState(_syncState.toSyncing(), generation);

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
      if (!_isCurrent(generation)) return result;

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
        await _processConversationResults(result, generation);
      } else if (checkFlashStall &&
          _walService.getSyncs().flashStallReason == FlashSyncStallReason.recordingSuspected) {
        // The pendant drain starved while the device kept minting new flash
        // pages: it is recording, and the protocol cannot serve stored pages
        // during an open recording session. Without this branch the state
        // falls through to `toCompleted` and the user is never told why
        // nothing synced.
        DebugLogManager.logWarning('SyncProvider: $context stalled — pendant appears to be recording');
        _updateSyncState(_syncState.toError(message: _pendantRecordingMessage()), generation);
      } else if (checkFlashStall && _walService.getSyncs().flashStallReason == FlashSyncStallReason.deviceFull) {
        // The pendant's flash is full: it halts recording (red LED flash) but
        // stays armed in recording mode and serves no pages in that state, so
        // the drain starves with the newest-page pointer frozen. Stopping
        // recording via the hardware button is what unfreezes the firmware.
        DebugLogManager.logWarning('SyncProvider: $context stalled — pendant storage is full');
        _updateSyncState(_syncState.toError(message: _pendantFullMessage()), generation);
      } else if ((result?.localUploadFailures ?? 0) == 0) {
        DebugLogManager.logInfo('SyncProvider: $context completed with no new conversations');
        _updateSyncState(_syncState.toCompleted(conversations: []), generation);
      }

      if (!_isCurrent(generation)) return result;

      // Client-side upload aborts (leave/background mid-multipart, #4587) leave
      // WALs as `miss`. Soft-retry only when failures are transient; permanent
      // server refusals (400/413) still surface SyncStatus.error.
      final permanentFailures = result?.localUploadPermanentFailures ?? 0;
      final localFailures = result?.localUploadFailures ?? 0;
      if (permanentFailures > 0) {
        final hint = result?.localUploadPermanentError;
        final errorMessage = _formatSyncError(
          hint != null ? Exception(hint) : Exception('Upload failed unexpectedly'),
          failedWal,
        );
        DebugLogManager.logWarning('SyncProvider: $context had $permanentFailures permanent local upload failure(s)');
        _updateSyncState(_syncState.toError(message: errorMessage, failedWal: failedWal), generation);
      } else if (localFailures > 0) {
        DebugLogManager.logWarning(
          'SyncProvider: $context had $localFailures transient local upload failure(s); re-arming recovery',
        );
        _updateSyncState(_syncState.toIdle(), generation);
        // Coordinator drains use rethrowOnError and schedule their own cooldown
        // via RecordingTransferCoordinator._runPass — do not double-wake here.
        if (_startBackgroundSync && !rethrowOnError) {
          unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
        }
      }
      return result;
    } catch (e) {
      if (!_isCurrent(generation)) {
        if (rethrowOnError) rethrow;
        return null;
      }
      if (isTransientNetworkError(e)) {
        DebugLogManager.logWarning('SyncProvider: $context hit transient network error; re-arming recovery: $e');
        _updateSyncState(_syncState.toIdle(), generation);
        // Wake only for direct/manual calls; coordinator owns retry scheduling.
        if (_startBackgroundSync && !rethrowOnError) {
          unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
        }
        if (rethrowOnError) rethrow;
        return null;
      }
      final errorMessage = _formatSyncError(e, failedWal);
      Logger.debug('SyncProvider: Error in $context: $errorMessage');
      DebugLogManager.logError(e, null, 'SyncProvider: $context failed: $errorMessage', {
        if (failedWal != null) 'walId': failedWal.id,
        if (failedWal != null) 'walStorage': failedWal.storage.toString(),
      });
      _updateSyncState(_syncState.toError(message: errorMessage, failedWal: failedWal), generation);
      if (rethrowOnError) rethrow;
      return null;
    } finally {
      await _keepAlive.release();
      // Use the admitted token, never a fresh `_sessionGeneration` read: a
      // finally refresh that recaptured would load this session's WAL list
      // into the account that replaced it, and `_recordNewlyAcceptedUploads`
      // would let those ids suppress the next session's progress.
      if (_isCurrent(generation)) {
        await _refreshWals(generation);
        if (_isCurrent(generation)) {
          _recordNewlyAcceptedUploads();
        }
      }
    }
  }

  void _recordNewlyAcceptedUploads() {
    final after = uploadedWals.map((w) => w.id).toSet();
    _trackedServerJobWalIds.addAll(after.difference(_uploadedWalIdsAtSyncStart));
  }

  bool _hasConversationResults(SyncLocalFilesResponse result) {
    return result.newConversationIds.isNotEmpty || result.updatedConversationIds.isNotEmpty;
  }

  String _pendantRecordingMessage() {
    // Providers have no BuildContext; use the global navigator's context for
    // l10n (same pattern as ai_app_generator_provider) with an English
    // fallback for headless/test runs where no widget tree exists.
    final l10n = globalNavigatorKey.currentContext?.l10n;
    return l10n?.pendantRecordingSyncBlocked ??
        'Your Pendant is still recording, so its stored audio can\'t be transferred. '
            'Press the Pendant\'s button to stop recording, then sync again.';
  }

  String _pendantFullMessage() {
    final l10n = globalNavigatorKey.currentContext?.l10n;
    return l10n?.pendantFullSyncBlocked ??
        'Your Pendant\'s storage is full and it\'s still in recording mode, so its stored audio '
            'can\'t be transferred. Press the Pendant\'s button to stop recording, then sync again.';
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
      // Keep state locale-neutral; the sync pages resolve this code through
      // AppLocalizations at render time.
      return pendingUploadErrorCode;
    }

    if (wal != null) {
      final walInfo = '${secondsToHumanReadable(wal.seconds)} (${wal.codec.toFormattedString()})';
      final source = wal.storage == WalStorage.sdcard ? 'SD card' : 'phone';
      return 'Failed to process $source audio file $walInfo: $baseMessage';
    }

    return baseMessage;
  }

  Future<void> retrySync() async {
    final generation = _sessionGeneration;
    final failedWal = _syncState.failedWal;
    // A deterministic too_large refusal is the one failed upload a retry can
    // never fix — the same bytes are the same size — so the error card's
    // Retry falls through to work that can still move (the row's own Delete
    // owns the too-large recording).
    if (failedWal != null &&
        (failedWal.status == WalStatus.miss || failedWal.status == WalStatus.uploadRejected) &&
        failedWal.uploadRejectionReason != WalUploadRejection.tooLarge) {
      await syncWal(failedWal);
      return;
    }
    if (retryableAttentionWals.isNotEmpty) {
      await retryNeedsAttentionWals();
      return;
    }
    if (_startBackgroundSync) {
      await _wakeTransfer(WakeTrigger.userRetry);
      return;
    }
    await _syncWalsDirect(generation);
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

  Future<void> _processConversationResults(SyncLocalFilesResponse result, int generation) async {
    if (!_isCurrent(generation)) return;
    _updateSyncState(_syncState.toFetchingConversations(), generation);
    final conversations = await ConversationSyncUtils.processConversationIds(
      newConversationIds: result.newConversationIds,
      updatedConversationIds: result.updatedConversationIds,
    );
    if (!_isCurrent(generation)) return;
    // Refresh WAL list so we can filter "synced" conversations to only those
    // whose WALs have been reconciled to WalStatus.synced.
    await _refreshWals(generation);
    if (!_isCurrent(generation)) return;
    final filtered = filterFullySyncedConversations(conversations: conversations, wals: _allWals);
    _updateSyncState(_syncState.toCompleted(conversations: filtered), generation);
  }

  /// Filters "synced" conversation pointers down to only those conversations
  /// whose associated WALs have been fully reconciled (`WalStatus.synced`).
  ///
  /// This prevents UI states like "synced OK" from showing up while some
  /// recordings are still left in an uploaded/pending state (issue #7240).
  @visibleForTesting
  static List<SyncedConversationPointer> filterFullySyncedConversations({
    required List<SyncedConversationPointer> conversations,
    required List<Wal> wals,
  }) {
    final byConversationId = <String, List<Wal>>{};
    for (final wal in wals) {
      final id = wal.conversationId;
      if (id == null) continue;
      (byConversationId[id] ??= <Wal>[]).add(wal);
    }

    bool isFullySynced(SyncedConversationPointer pointer) {
      if (pointer.conversation.isHiddenFromDefaultList) return false;
      final walsForConversation = byConversationId[pointer.conversation.id] ?? const <Wal>[];
      if (walsForConversation.isEmpty) return true; // No local WALs → nothing pending.
      return walsForConversation.every((w) => w.status == WalStatus.synced);
    }

    final latestById = {for (final pointer in conversations) pointer.conversation.id: pointer};
    return latestById.values.where(isFullySynced).toList();
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

  Future<void> shareRecordingAsWav(List<Wal> wals) => _audioPlayerUtils.shareRecordingAsAudio(wals);

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
  void onWalUpdated() {
    if (_isDisposed) return;
    _walUpdatePending = true;
    _scheduleWalUpdate();
  }

  void _cancelQueuedWalUpdates() {
    _walUpdateTimer?.cancel();
    _walUpdateTimer = null;
    _walUpdatePending = false;
  }

  void _scheduleWalUpdate() {
    if (_isDisposed || !_walUpdatePending || _walUpdateTimer != null || _walUpdateRefresh != null) return;
    final generation = _sessionGeneration;
    _walUpdateTimer = Timer(_uiPublishInterval, () {
      _walUpdateTimer = null;
      if (!_isCurrent(generation) || _walUpdateRefresh != null) return;
      final refresh = _refreshWals(generation);
      _walUpdateRefresh = refresh;
      unawaited(refresh.whenComplete(() {
        if (!identical(_walUpdateRefresh, refresh)) return;
        _walUpdateRefresh = null;
        // Events during a slow read still get a trailing snapshot. Never
        // overlap background reads of the complete inventory.
        _scheduleWalUpdate();
      }));
    });
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {
    final generation = _admittedWorkGeneration;
    if (!_isCurrent(generation)) return;
    // Completions arrive once per recording fragment — a reconcile pass over a
    // large backlog delivers dozens within a second. The per-event work here is
    // O(1); the inventory refresh and its publications ride the same coalesced
    // window as [onWalUpdated] (see [_publishSyncedCompletions]), so a burst
    // costs one refresh and still publishes the final state.
    if (wal.status == WalStatus.uploaded || wal.status == WalStatus.synced) {
      _captureWedgeMonitor.onUploadCompleted();
    }
    if (_totalWalsToProcess > 0) _walsProcessedCount++;
    _walUpdatePending = true;
    _scheduleWalUpdate();
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
    if (!_isCurrent(_admittedWorkGeneration) || !_syncState.isSyncing) {
      return;
    }

    final incomingPhase = phase ?? _syncState.phase;
    var nextCurrent = currentFile ?? _syncState.currentFile;
    var nextTotal = totalFiles ?? _syncState.totalFiles;

    // Per-chunk device downloads report 1/1; do not clobber multi-recording upload counts.
    if (incomingPhase == SyncPhase.downloadingFromDevice && totalFiles == 1 && (_syncState.totalFiles ?? 0) > 1) {
      nextCurrent = _syncState.currentFile;
      nextTotal = _syncState.totalFiles;
    }

    final progress = percentage.clamp(0.0, 1.0);
    final previous = _syncState;
    if (previous.progress == progress &&
        previous.phase == incomingPhase &&
        previous.speedKBps == speedKBps &&
        previous.currentFile == nextCurrent &&
        previous.totalFiles == nextTotal &&
        previous.uploadedBytes == uploadedBytes &&
        previous.totalBytesToUpload == totalBytesToUpload) {
      return;
    }

    final next = previous.toSyncing(
      progress: progress,
      speedKBps: speedKBps,
      phase: incomingPhase,
      currentFile: nextCurrent,
      totalFiles: nextTotal,
      uploadedBytes: uploadedBytes,
      totalBytesToUpload: totalBytesToUpload,
    );
    if (previous.phase != incomingPhase ||
        previous.currentFile != nextCurrent ||
        previous.totalFiles != nextTotal ||
        (previous.progress < 1 && progress == 1)) {
      _updateSyncState(next, _admittedWorkGeneration);
      return;
    }
    _syncState = next;
    final generation = _admittedWorkGeneration;
    _progressNotifyTimer ??= Timer(_uiPublishInterval, () {
      _progressNotifyTimer = null;
      if (_isCurrent(generation) && _syncState.isSyncing) notifyListeners();
    });
  }

  /// Cancel ongoing sync operation.
  /// If batches already completed, immediately shows their conversation results.
  void cancelSync() {
    final generation = _sessionGeneration;
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
      unawaited(_processConversationResults(partialResults, generation));
    } else {
      _updateSyncState(_syncState.toIdle(), generation);
    }
    // Drop the Android transfer FGS immediately so screen-off keep-alive
    // cannot outlive a user cancel (#5221).
    unawaited(_keepAlive.releaseAll());
    if (!_isCurrent(generation)) return;
    // Cancel only stops further uploads. Recordings already `uploaded` are
    // safe on the server — keep reconciling them through the single owner.
    unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
  }

  /// Transfer a single WAL from device storage (SD card or flash page) to phone storage
  Future<void> transferWalToPhone(Wal wal) async {
    final generation = _sessionGeneration;
    if (wal.storage != WalStorage.sdcard && wal.storage != WalStorage.flashPage) {
      throw Exception('This recording is already on phone');
    }

    _updateSyncState(_syncState.toSyncing(), generation);

    await _keepAlive.acquire();
    try {
      await _walService.getSyncs().syncWal(wal: wal, progress: this);
      await _refreshWals(generation);
      _updateSyncState(_syncState.toIdle(), generation);
    } catch (e) {
      await _refreshWals(generation);
      _updateSyncState(_syncState.toIdle(), generation);
      rethrow;
    } finally {
      await _keepAlive.release();
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

  /// Server-side processing progress after uploads returned 202 (uploaded WALs
  /// still reconciling). Completed = recordings no longer waiting on a job.
  ({int processed, int total}) get offlineServerProcessingCounts {
    return OfflineProcessingDisplay.serverJobCounts(trackedUploadedWalIds: _trackedServerJobWalIds, wals: _allWals);
  }

  /// [offlineServerProcessingCounts] in seconds of audio, for the status card.
  ({int doneSeconds, int totalSeconds, bool tracked}) get offlineServerProcessingSeconds {
    return OfflineProcessingDisplay.serverJobSeconds(trackedUploadedWalIds: _trackedServerJobWalIds, wals: _allWals);
  }

  @override
  void dispose() {
    _cancelQueuedWalUpdates();
    _walUpdateRefresh = null;
    _progressNotifyTimer?.cancel();
    _progressNotifyTimer = null;
    _periodicSync?.dispose();
    _isDisposed = true;
    _sessionGeneration++;
    _admittedWorkGeneration = -1;
    unawaited(_keepAlive.releaseAll());
    _audioPlayerUtils.removeListener(_onAudioPlayerStateChanged);
    SyncRateLimiter.instance.removeListener(_onRateLimiterChanged);
    WaveformUtils.clearCache();
    _walService.unsubscribe(this);
    super.dispose();
  }
}
