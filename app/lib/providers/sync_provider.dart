import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/conversation_sync_utils.dart';
import 'package:omi/utils/waveform_utils.dart';

enum WalStatusFilter { pending, synced }

enum WalDisplayFilter { all, pending, synced }

class SyncProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  // Services
  final AudioPlayerUtils _audioPlayerUtils = AudioPlayerUtils.instance;

  // WAL management
  List<Wal> _allWals = [];
  List<Wal> get allWals => _allWals;
  bool _isLoadingWals = false;
  bool get isLoadingWals => _isLoadingWals;

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
  // pending counts until the reconciler confirms it `synced`.
  List<Wal> get pendingWals => _allWals
      .where((w) =>
          w.status == WalStatus.miss ||
          w.status == WalStatus.uploaded ||
          w.status == WalStatus.corrupted ||
          w.isSyncing)
      .toList();

  List<Wal> get uploadedWals => _allWals.where((w) => w.status == WalStatus.uploaded).toList();

  List<Wal> get pendingDeletableWals =>
      _allWals.where((w) => !w.isSyncing && (w.status == WalStatus.miss || w.status == WalStatus.corrupted)).toList();

  List<Wal> get syncedWals => _allWals.where((w) => w.status == WalStatus.synced).toList();

  /// True while a fair-use (429) cooldown is active — uploads are paused.
  bool get isRateLimited => SyncRateLimiter.instance.isLimited;
  DateTime? get rateLimitedUntil => SyncRateLimiter.instance.until;

  List<Wal> get filteredByStatusWals {
    if (_statusFilter == WalStatusFilter.pending) {
      return pendingWals;
    }
    return syncedWals;
  }

  // ─────────────────────────────────────────
  // Redesigned auto-sync page: unified self-describing list
  // (additive — does not touch the legacy SyncPage API above)
  // ─────────────────────────────────────────

  /// All recordings, newest first. The redesigned list shows synced and
  /// unsynced recordings together so backed-up work is never hidden behind a
  /// tab the user has to discover.
  List<Wal> get displaySortedWals {
    final list = List<Wal>.from(_allWals);
    list.sort((a, b) => b.timerStart.compareTo(a.timerStart));
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
          return w.syncDisplayState != WalSyncDisplayState.synced;
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
  Timer? _autoUploadTimer;
  bool _isDisposed = false;

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
  List<SyncedConversationPointer> get syncedConversationsPointers => _syncState.syncedConversations;
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

  IWalService get _walService => ServiceManager.instance().wal;

  SyncProvider() {
    _walService.subscribe(this, this);
    _audioPlayerUtils.addListener(_onAudioPlayerStateChanged);
    _initializeProvider();
  }

  void _initializeProvider() async {
    await refreshWals();
    if (_isDisposed) return;
    _attachReconciler();
    _scheduleAutoUploadPendingPhoneFiles();
  }

  /// Wire the background reconciler to the phone sync + our conversation
  /// surfacing, then poke once to resume any recordings left `uploaded` by a
  /// previous session (app-kill recovery).
  void _attachReconciler() {
    try {
      final phone = _walService.getSyncs().phone;
      SyncReconciler.instance.attach(phone, _onReconciledConversations);
      SyncReconciler.instance.poke();
    } catch (e) {
      Logger.debug('SyncProvider: attach reconciler failed: $e');
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

  bool _isAutoUploading = false;

  /// Auto-upload phone WALs to cloud on app open when device is not connected
  /// and no sync is already in progress.
  void _scheduleAutoUploadPendingPhoneFiles() {
    _autoUploadTimer?.cancel();
    _autoUploadTimer = Timer(const Duration(seconds: 3), () {
      _autoUploadTimer = null;
      _autoUploadPendingPhoneFiles();
    });
  }

  void _autoUploadPendingPhoneFiles() async {
    if (_isDisposed) return;
    if (_syncState.isProcessing) return;
    if (_walService.getSyncs().isStorageSyncing || _walService.getSyncs().isSdCardSyncing) return;
    final phoneWals = _allWals
        .where((w) => w.status == WalStatus.miss && (w.storage == WalStorage.disk || w.storage == WalStorage.mem))
        .toList();
    if (phoneWals.isEmpty) return;
    Logger.debug('SyncProvider: Auto-uploading ${phoneWals.length} pending phone files to cloud');
    _isAutoUploading = true;
    await _performSync(
      operation: () => _walService.getSyncs().phone.syncAll(progress: this),
      context: 'auto-upload phone files',
    );
    _isAutoUploading = false;
  }

  /// Cancel auto-upload if running. Called before device-triggered sync.
  void _cancelAutoUploadIfNeeded() {
    if (_isAutoUploading) {
      Logger.debug('SyncProvider: Cancelling auto-upload for device sync');
      _walService.getSyncs().phone.cancelSync();
      _isAutoUploading = false;
    }
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

  Future<void> syncWals({IWifiConnectionListener? connectionListener}) async {
    _cancelAutoUploadIfNeeded();
    _updateSyncState(_syncState.toIdle());
    _totalWalsToProcess = missingWals.length;
    _walsProcessedCount = 0;
    await _performSync(
      operation: () => _walService.getSyncs().syncAll(progress: this, connectionListener: connectionListener),
      context: 'sync all WALs',
    );
  }

  Future<void> syncWal(Wal wal, {IWifiConnectionListener? connectionListener}) async {
    _cancelAutoUploadIfNeeded();
    _updateSyncState(_syncState.toIdle());
    await _performSync(
      operation: () => _walService.getSyncs().syncWal(wal: wal, progress: this, connectionListener: connectionListener),
      context: 'sync WAL ${wal.id}',
      failedWal: wal,
    );
  }

  Future<void> _performSync({
    required Future<SyncLocalFilesResponse?> Function() operation,
    required String context,
    Wal? failedWal,
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
        return;
      }

      if (result != null && _hasConversationResults(result)) {
        Logger.debug(
          'SyncProvider: $context returned ${result.newConversationIds.length} new, ${result.updatedConversationIds.length} updated conversations',
        );
        DebugLogManager.logInfo('SyncProvider: $context succeeded', {
          'newConversations': result.newConversationIds.length,
          'updatedConversations': result.updatedConversationIds.length,
        });
        await _processConversationResults(result);
      } else {
        DebugLogManager.logInfo('SyncProvider: $context completed with no new conversations');
        _updateSyncState(_syncState.toCompleted(conversations: []));
      }
      // Uploads just finished — recordings are now `uploaded`. Kick the
      // reconciler so their conversations stream in without the user waiting.
      SyncReconciler.instance.poke();
    } catch (e) {
      final errorMessage = _formatSyncError(e, failedWal);
      Logger.debug('SyncProvider: Error in $context: $errorMessage');
      DebugLogManager.logError(e, null, 'SyncProvider: $context failed: $errorMessage', {
        if (failedWal != null) 'walId': failedWal.id,
        if (failedWal != null) 'walStorage': failedWal.storage.toString(),
      });
      _updateSyncState(_syncState.toError(message: errorMessage, failedWal: failedWal));
    }
  }

  bool _hasConversationResults(SyncLocalFilesResponse result) {
    return result.newConversationIds.isNotEmpty || result.updatedConversationIds.isNotEmpty;
  }

  String _formatSyncError(dynamic error, Wal? wal) {
    var baseMessage = error.toString().replaceAll('Exception: ', '').replaceAll('WifiSyncException: ', '');

    // Convert technical WiFi errors to user-friendly messages
    if (baseMessage.toLowerCase().contains('internal error') ||
        baseMessage.toLowerCase().contains('invalidpacketlength') ||
        baseMessage.toLowerCase().contains('packet length')) {
      baseMessage = 'Failed to enable WiFi on device';
    } else if (baseMessage.toLowerCase().contains('wifi') && baseMessage.toLowerCase().contains('setup')) {
      baseMessage = 'Failed to enable WiFi on device';
    } else if (baseMessage.toLowerCase().contains('tcp') || baseMessage.toLowerCase().contains('socket')) {
      baseMessage = 'Connection interrupted';
    } else if (baseMessage.toLowerCase().contains('timeout')) {
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
    final failedWal = _syncState.failedWal;
    if (failedWal != null) {
      await syncWal(failedWal);
    } else {
      await syncWals();
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
    // safe on the server — keep reconciling them.
    SyncReconciler.instance.poke();
  }

  /// Transfer a single WAL from device storage (SD card or flash page) to phone storage
  Future<void> transferWalToPhone(Wal wal, {IWifiConnectionListener? connectionListener}) async {
    if (wal.storage != WalStorage.sdcard && wal.storage != WalStorage.flashPage) {
      throw Exception('This recording is already on phone');
    }

    // Set sync state to syncing so progress updates are processed
    _updateSyncState(_syncState.toSyncing());

    try {
      await _walService.getSyncs().syncWal(wal: wal, progress: this, connectionListener: connectionListener);
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
    _autoUploadTimer?.cancel();
    _autoUploadTimer = null;
    _audioPlayerUtils.removeListener(_onAudioPlayerStateChanged);
    WaveformUtils.clearCache();
    _walService.unsubscribe(this);
    super.dispose();
  }
}
