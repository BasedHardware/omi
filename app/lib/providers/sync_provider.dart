import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/time_utils.dart';

import '../utils/audio_player_utils.dart';
import '../utils/waveform_utils.dart';
import '../models/sync_state.dart';
import '../utils/conversation_sync_utils.dart';

class SyncProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  // Services
  final AudioPlayerUtils _audioPlayerUtils = AudioPlayerUtils();

  // WAL management
  List<Wal> _allWals = [];
  List<Wal> get allWals => _allWals;
  bool _isLoadingWals = false;
  bool get isLoadingWals => _isLoadingWals;

  // Storage filter
  WalStorage? _storageFilter;
  WalStorage? get storageFilter => _storageFilter;

  List<Wal> get filteredWals {
    if (_storageFilter == null) {
      return _allWals;
    }
    
    // SD Card filter: show WALs on SD card OR transferred from SD card
    if (_storageFilter == WalStorage.sdcard) {
      return _allWals.where((wal) => 
        wal.storage == WalStorage.sdcard || 
        wal.originalStorage == WalStorage.sdcard
      ).toList();
    }
    
    // Phone filter: show WALs on phone that are NOT originally from SD card
    if (_storageFilter == WalStorage.disk || _storageFilter == WalStorage.mem) {
      return _allWals.where((wal) => 
        (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
        wal.originalStorage != WalStorage.sdcard
      ).toList();
    }
    
    // Other filters (flashPage, etc.)
    return _allWals.where((wal) => wal.storage == _storageFilter).toList();
  }

  // Sync state
  SyncState _syncState = const SyncState();
  SyncState get syncState => _syncState;

  // Track initial missing WALs count for progress calculation
  int _initialMissingWalsCount = 0;

  // Computed properties for backward compatibility
  List<Wal> get missingWals => filteredWals.where((w) => w.status == WalStatus.miss).toList();
  int get missingWalsInSeconds =>
      missingWals.isEmpty ? 0 : missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

  // Backward compatibility getters
  bool get isSyncing => _syncState.isSyncing;
  bool get syncCompleted => _syncState.isCompleted;
  bool get isFetchingConversations => _syncState.isFetchingConversations;
  double get walsSyncedProgress => _syncState.progress;
  double? get syncSpeedKBps => _syncState.speedKBps;
  List<SyncedConversationPointer> get syncedConversationsPointers => _syncState.syncedConversations;
  String? get syncError => _syncState.errorMessage;
  Wal? get failedWal => _syncState.failedWal;

  // Flash page (Limitless) sync states - distinct phases
  // isSyncingFromPendant: true when receiving data from pendant (pendant → phone)
  // isUploadingToCloud: true when uploading files to cloud (phone → cloud)
  bool get isSyncingFromPendant => _walService.getSyncs().flashPage.isSyncing;
  bool get isUploadingToCloud => _walService.getSyncs().flashPage.isUploading;
  bool get hasOrphanedFiles => _walService.getSyncs().flashPage.hasOrphanedFiles;
  int get orphanedFilesCount => _walService.getSyncs().flashPage.orphanedFilesCount;

  // SD Card transfer state (persists across navigation)
  String? _transferringWalId;
  double _transferProgress = 0.0;
  double? _transferSpeedKBps;
  int? _transferEtaSeconds;
  int _transferTotalBytes = 0;
  bool _isTransferring = false;

  String? get transferringWalId => _transferringWalId;
  double get transferProgress => _transferProgress;
  double? get transferSpeedKBps => _transferSpeedKBps;
  int? get transferEtaSeconds => _transferEtaSeconds;
  bool get isTransferring => _isTransferring;

  /// Check if a specific WAL is currently being transferred (via direct transfer or batch sync)
  bool isWalTransferring(String walId) {
    // Check direct transfer state
    if (_isTransferring && _transferringWalId == walId) {
      return true;
    }
    // Check if WAL is syncing via batch syncAll()
    final wal = getWalById(walId);
    return wal?.isSyncing ?? false;
  }

  /// Get a WAL by ID from the current list
  Wal? getWalById(String walId) {
    try {
      return _allWals.firstWhere((w) => w.id == walId);
    } catch (e) {
      return null;
    }
  }

  /// Get transfer progress for a specific WAL (returns null if not transferring)
  double? getWalTransferProgress(String walId) {
    // Check direct transfer state first
    if (_transferringWalId == walId && _isTransferring) {
      return _transferProgress;
    }
    // Check if WAL is syncing via batch syncAll() - use WAL's storage offset for progress
    final wal = getWalById(walId);
    if (wal != null && wal.isSyncing && wal.storage == WalStorage.sdcard) {
      final total = wal.storageTotalBytes - wal.storageOffset;
      if (total > 0 && wal.storageOffset > 0) {
        // Calculate progress based on how much has been downloaded
        // Note: storageOffset updates during download
        return _syncState.progress;
      }
      return _syncState.progress > 0 ? _syncState.progress : null;
    }
    return null;
  }

  /// Get transfer speed for a specific WAL (returns null if not transferring)
  double? getWalTransferSpeed(String walId) {
    // Check direct transfer state first
    if (_transferringWalId == walId && _isTransferring) {
      return _transferSpeedKBps;
    }
    // Check if WAL is syncing via batch syncAll()
    final wal = getWalById(walId);
    if (wal != null && wal.isSyncing && wal.storage == WalStorage.sdcard) {
      return _syncState.speedKBps;
    }
    return null;
  }

  /// Get transfer ETA for a specific WAL (returns null if not transferring)
  int? getWalTransferEta(String walId) {
    // Check direct transfer state first
    if (_transferringWalId == walId && _isTransferring) {
      return _transferEtaSeconds;
    }
    // Check if WAL is syncing via batch syncAll()
    final wal = getWalById(walId);
    if (wal != null && wal.isSyncing && wal.storage == WalStorage.sdcard) {
      return wal.syncEtaSeconds;
    }
    return null;
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
    debugPrint('SyncProvider: Loaded ${_allWals.length} WALs (${missingWals.length} missing)');

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

  Future<void> syncWals() async {
    _updateSyncState(_syncState.toIdle());
    _initialMissingWalsCount = missingWals.length;
    await _performSync(
      operation: () => _walService.getSyncs().syncAll(progress: this),
      context: 'sync all WALs',
    );
  }

  Future<void> syncWal(Wal wal) async {
    _updateSyncState(_syncState.toIdle());
    await _performSync(
      operation: () => _walService.getSyncs().syncWal(wal: wal, progress: this),
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
        debugPrint('SyncProvider: Two-phase sync - ${sdCardWals.length} SD card files will be downloaded first');
      }

      final result = await operation();

      if (result != null && _hasConversationResults(result)) {
        debugPrint(
            'SyncProvider: $context returned ${result.newConversationIds.length} new, ${result.updatedConversationIds.length} updated conversations');
        await _processConversationResults(result);
      } else {
        _updateSyncState(_syncState.toCompleted(conversations: []));
      }
    } catch (e) {
      final errorMessage = _formatSyncError(e, failedWal);
      debugPrint('SyncProvider: Error in $context: $errorMessage');
      _updateSyncState(_syncState.toError(message: errorMessage, failedWal: failedWal));
    }
  }

  bool _hasConversationResults(SyncLocalFilesResponse result) {
    return result.newConversationIds.isNotEmpty || result.updatedConversationIds.isNotEmpty;
  }

  String _formatSyncError(dynamic error, Wal? wal) {
    final baseMessage = error.toString().replaceAll('Exception: ', '');

    if (wal != null) {
      final walInfo = '${secondsToHumanReadable(wal.seconds)} (${wal.codec.toFormattedString()})';
      final source = wal.storage == WalStorage.sdcard ? 'SD card' : 'phone';
      return 'Failed to process $source audio file $walInfo: $baseMessage';
    }

    return 'Error processing audio files: $baseMessage';
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

    return await compute(_generateWaveformInBackground, {
      'walId': walId,
      'wavFilePath': wavFilePath,
    });
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
      final walProgress = walBasedProgress;
      _updateSyncState(_syncState.toSyncing(progress: walProgress));
    }
  }

  @override
  void onStatusChanged(WalServiceStatus status) {
    debugPrint('SyncProvider: WAL service status changed to $status');
  }

  @override
  void onWalSyncedProgress(double percentage, {double? speedKBps}) {
    if (_syncState.isSyncing) {
      _updateSyncState(_syncState.toSyncing(progress: percentage, speedKBps: speedKBps));
    }
  }

  /// Cancel ongoing sync operation
  void cancelSync() {
    _walService.getSyncs().cancelSync();
    _clearTransferState();
    _updateSyncState(_syncState.toIdle());
  }

  void _clearTransferState() {
    _transferringWalId = null;
    _transferProgress = 0.0;
    _transferSpeedKBps = null;
    _transferEtaSeconds = null;
    _transferTotalBytes = 0;
    _isTransferring = false;
    notifyListeners();
  }

  /// Transfer a single SD card WAL to phone storage (without cloud upload)
  Future<void> transferSdCardWalToPhone(Wal wal) async {
    if (wal.storage != WalStorage.sdcard) {
      throw Exception('This recording is not on SD card');
    }

    // Set transfer state
    _transferringWalId = wal.id;
    _transferProgress = 0.0;
    _transferSpeedKBps = null;
    _transferEtaSeconds = null;
    _transferTotalBytes = wal.storageTotalBytes - wal.storageOffset;
    _isTransferring = true;
    notifyListeners();

    // Create a custom progress listener that updates provider state
    final progressListener = _TransferProgressListener((progress, speedKBps) {
      _transferProgress = progress;
      _transferSpeedKBps = speedKBps;
      
      // Calculate ETA based on remaining bytes and speed
      if (speedKBps != null && speedKBps > 0 && progress < 1.0) {
        final remainingBytes = _transferTotalBytes * (1.0 - progress);
        _transferEtaSeconds = (remainingBytes / 1024 / speedKBps).round();
      } else {
        _transferEtaSeconds = null;
      }
      
      notifyListeners();
    });

    try {
      await _walService.getSyncs().syncWal(wal: wal, progress: progressListener);
      await refreshWals();
    } catch (e) {
      await refreshWals();
      rethrow;
    } finally {
      _clearTransferState();
    }
  }

  /// Check if SD card sync is in progress
  bool get isSdCardSyncing => _walService.getSyncs().isSdCardSyncing;

  // Calculate progress based on WALs synced
  double get walBasedProgress {
    if (_initialMissingWalsCount == 0) return 0.0;
    final currentMissingCount = missingWals.length;
    final syncedCount = _initialMissingWalsCount - currentMissingCount;
    return (syncedCount / _initialMissingWalsCount).clamp(0.0, 1.0);
  }

  // Get the number of WALs processed
  int get processedWalsCount {
    if (_initialMissingWalsCount == 0) return 0;
    final currentMissingCount = missingWals.length;
    return _initialMissingWalsCount - currentMissingCount;
  }

  // Get the initial missing WALs count
  int get initialMissingWalsCount => _initialMissingWalsCount;

  @override
  void dispose() {
    _audioPlayerUtils.removeListener(_onAudioPlayerStateChanged);
    _audioPlayerUtils.dispose();
    WaveformUtils.clearCache();
    _walService.unsubscribe(this);
    super.dispose();
  }
}

/// Helper class for tracking transfer progress
class _TransferProgressListener implements IWalSyncProgressListener {
  final void Function(double progress, double? speedKBps)? onProgress;

  _TransferProgressListener(this.onProgress);

  @override
  void onWalSyncedProgress(double percentage, {double? speedKBps}) {
    onProgress?.call(percentage, speedKBps);
  }
}
