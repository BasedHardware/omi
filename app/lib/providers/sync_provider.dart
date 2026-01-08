import 'dart:async';
import 'package:flutter/foundation.dart';
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
          .where((wal) =>
              (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
              wal.originalStorage != WalStorage.sdcard &&
              wal.originalStorage != WalStorage.flashPage)
          .toList();
    }

    // Other filters
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
    _updateSyncState(_syncState.toIdle());
  }

  /// Transfer a single WAL from device storage (SD card or flash page) to phone storage
  Future<void> transferWalToPhone(Wal wal) async {
    if (wal.storage != WalStorage.sdcard && wal.storage != WalStorage.flashPage) {
      throw Exception('This recording is already on phone');
    }

    // Set sync state to syncing so progress updates are processed
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
