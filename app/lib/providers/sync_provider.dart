import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/time_utils.dart';

import '../services/audio_player_service.dart';
import '../services/waveform_service.dart';
import '../models/sync_state.dart';
import '../services/conversation_sync_service.dart';

class SyncProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  // Services
  final AudioPlayerService _audioPlayerService = AudioPlayerService();
  final WaveformService _waveformService = WaveformService();
  final ConversationSyncService _conversationSyncService = ConversationSyncService();

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
  List<SyncedConversationPointer> get syncedConversationsPointers => _syncState.syncedConversations;
  String? get syncError => _syncState.errorMessage;
  Wal? get failedWal => _syncState.failedWal;

  // Audio playback delegates
  String? get currentPlayingWalId => _audioPlayerService.currentPlayingWalId;
  bool get isProcessingAudio => _audioPlayerService.isProcessingAudio;
  bool get isSharingAudio => _audioPlayerService.isSharingAudio;
  bool isWalSharing(String walId) => _audioPlayerService.isWalSharing(walId);
  Duration get currentPosition => _audioPlayerService.currentPosition;
  Duration get totalDuration => _audioPlayerService.totalDuration;
  double get playbackProgress => _audioPlayerService.playbackProgress;

  IWalService get _walService => ServiceManager.instance().wal;

  SyncProvider() {
    _walService.subscribe(this, this);
    _audioPlayerService.addListener(_onAudioPlayerStateChanged);
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

    try {
      _allWals = await _walService.getSyncs().getAllWals();
      debugPrint('SyncProvider: Loaded ${_allWals.length} WALs (${missingWals.length} missing)');
    } catch (e) {
      debugPrint('SyncProvider: Error refreshing WALs: $e');
      _allWals = [];
    } finally {
      _isLoadingWals = false;
      notifyListeners();
    }
  }

  Future<WalStats> getWalStats() async {
    try {
      return await _walService.getSyncs().getWalStats();
    } catch (e) {
      debugPrint('SyncProvider: Error getting WAL stats: $e');
      return _createEmptyWalStats();
    }
  }

  WalStats _createEmptyWalStats() {
    return WalStats(
      totalFiles: 0,
      phoneFiles: 0,
      sdcardFiles: 0,
      phoneSize: 0,
      sdcardSize: 0,
      syncedFiles: 0,
      missedFiles: 0,
    );
  }

  Future<void> deleteWal(Wal wal) async {
    try {
      await _walService.getSyncs().deleteWal(wal);
      await refreshWals();
    } catch (e) {
      debugPrint('SyncProvider: Error deleting WAL ${wal.id}: $e');
      rethrow;
    }
  }

  Future<void> deleteAllSyncedWals() async {
    try {
      await _walService.getSyncs().deleteAllSyncedWals();
      await refreshWals();
    } catch (e) {
      debugPrint('SyncProvider: Error deleting all synced WALs: $e');
      rethrow;
    }
  }

  Future<void> resyncWal(Wal wal) async {
    debugPrint("SyncProvider: Resyncing WAL ${wal.id}");
    _updateSyncState(_syncState.toIdle());

    await _performSync(
      operation: () => _walService.getSyncs().resyncWal(wal),
      context: 'resync WAL ${wal.id}',
      failedWal: wal,
    );
  }

  Future<void> syncWals() async {
    debugPrint("SyncProvider: Syncing all WALs");
    _updateSyncState(_syncState.toIdle());

    // Store initial missing WALs count for progress calculation
    _initialMissingWalsCount = missingWals.length;

    await _performSync(
      operation: () => _walService.getSyncs().syncAll(progress: this),
      context: 'sync all WALs',
    );
  }

  Future<void> syncWal(Wal wal) async {
    debugPrint("SyncProvider: Syncing WAL ${wal.id}");
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

    try {
      final conversations = await _conversationSyncService.processConversationIds(
        newConversationIds: result.newConversationIds,
        updatedConversationIds: result.updatedConversationIds,
      );

      _updateSyncState(_syncState.toCompleted(conversations: conversations));
    } catch (e) {
      debugPrint('SyncProvider: Error processing conversation results: $e');
      _updateSyncState(_syncState.toError(
        message: 'Failed to fetch conversation details: ${e.toString()}',
      ));
    }
  }

  // Audio playback delegate methods
  bool isWalPlaying(String walId) => _audioPlayerService.isWalPlaying(walId);
  bool canPlayOrShareWal(Wal wal) => _audioPlayerService.canPlayOrShareWal(wal);

  Future<void> toggleWalPlayback(Wal wal) async {
    await _audioPlayerService.toggleWalPlayback(wal);
  }

  Future<void> shareWalAsWav(Wal wal) async {
    await _audioPlayerService.shareWalAsWav(wal);
  }

  Future<void> seekToPosition(Duration position) async {
    await _audioPlayerService.seekToPosition(position);
  }

  Future<void> skipForward({Duration duration = const Duration(seconds: 10)}) async {
    await _audioPlayerService.skipForward(duration: duration);
  }

  Future<void> skipBackward({Duration duration = const Duration(seconds: 10)}) async {
    await _audioPlayerService.skipBackward(duration: duration);
  }

  // Waveform generation delegate method
  Future<List<double>?> getWaveformForWal(String walId) async {
    // Find the WAL by ID
    final wal = _allWals.firstWhere((w) => w.id == walId, orElse: () => throw Exception('WAL not found'));

    // Ensure WAV file exists for waveform generation
    String? wavFilePath = _audioPlayerService.getCachedWavPath(walId);
    if (wavFilePath == null && canPlayOrShareWal(wal)) {
      wavFilePath = await _audioPlayerService.ensureWavFileExists(wal);
    }

    // Use compute to run waveform generation on background thread
    return await compute(_generateWaveformInBackground, {
      'walId': walId,
      'wavFilePath': wavFilePath,
    });
  }

  // Static method for background waveform generation
  static Future<List<double>?> _generateWaveformInBackground(Map<String, dynamic> params) async {
    final String walId = params['walId'];
    final String? wavFilePath = params['wavFilePath'];

    // Create a new instance of WaveformService for the isolate
    final waveformService = WaveformService();
    return await waveformService.getWaveformForWal(walId, wavFilePath);
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
  void onWalSyncedProgress(double percentage) {
    if (_syncState.isSyncing) {
      _updateSyncState(_syncState.toSyncing(progress: percentage));
    }
  }

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
    _audioPlayerService.removeListener(_onAudioPlayerStateChanged);
    _audioPlayerService.dispose();
    _waveformService.clearCache();
    _walService.unsubscribe(this);
    super.dispose();
  }
}
