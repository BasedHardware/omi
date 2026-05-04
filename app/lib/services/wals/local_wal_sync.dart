import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:meta/meta.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/wal_file_manager.dart';

class LocalWalSyncImpl implements LocalWalSync {
  List<Wal> _wals = const [];

  List<WalFrame> _frames = [];
  List<bool> _frameSynced = [];

  Timer? _chunkingTimer;
  Timer? _flushingTimer;

  IWalSyncListener listener;

  int _framesPerSecond = 100;
  BleAudioCodec _codec = BleAudioCodec.opus;
  String? _deviceId;
  String? _deviceModel;

  bool _isCancelled = false;

  /// Completes when _initializeWals() finishes loading WALs from disk.
  final Completer<void> _walReady = Completer<void>();

  /// Future that resolves when WALs are loaded and ready to query.
  Future<void> get walReady => _walReady.future;

  /// Accumulated conversation IDs from completed batches during an ongoing sync.
  /// Accessible so that cancel can retrieve partial results.
  SyncLocalFilesResponse? _accumulatedResponse;
  SyncLocalFilesResponse? get accumulatedResponse => _accumulatedResponse;

  LocalWalSyncImpl(this.listener);

  @visibleForTesting
  List<WalFrame> get testFrames => _frames;

  @visibleForTesting
  List<bool> get testFrameSynced => _frameSynced;

  @visibleForTesting
  List<Wal> get testWals => _wals;

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  @override
  void cancelSync() {
    _isCancelled = true;
  }

  @override
  Future<void> addExternalWal(Wal wal) async {
    final existingIndex = _wals.indexWhere((w) => w.id == wal.id);
    if (existingIndex >= 0) {
      Logger.debug("LocalWalSync: WAL ${wal.id} already exists, skipping");
      return;
    }
    _wals.add(wal);
    await _saveWalsToFile();
    listener.onWalUpdated();
    Logger.debug("LocalWalSync: Added external WAL ${wal.id} (${wal.seconds}s)");
  }

  @override
  void start() {
    _initializeWals();
    _chunkingTimer = Timer.periodic(const Duration(seconds: chunkSizeInSeconds + newFrameSyncDelaySeconds), (t) async {
      await _chunk();
    });
    _flushingTimer = Timer.periodic(const Duration(seconds: flushIntervalInSeconds + newFrameSyncDelaySeconds), (
      t,
    ) async {
      await _flush();
    });
  }

  Future<void> _initializeWals() async {
    await WalFileManager.init();
    _wals = await WalFileManager.loadWals();
    Logger.debug("wal service start: ${_wals.length}");

    final missingCount = _wals.where((w) => w.status == WalStatus.miss).length;
    final syncedCount = _wals.where((w) => w.status == WalStatus.synced).length;
    DebugLogManager.logEvent('wal_initialized', {
      'totalWals': _wals.length,
      'missing': missingCount,
      'synced': syncedCount,
    });

    // Run migrations for legacy Limitless files
    final migratedCount = await WalFileManager.migrateLegacyLimitlessFiles(_wals);
    if (migratedCount > 0) {
      // Reload WALs after migration
      _wals = await WalFileManager.loadWals();
      Logger.debug("wal service after migration: ${_wals.length}");
      DebugLogManager.logInfo('WAL migration completed', {'migratedCount': migratedCount, 'totalAfter': _wals.length});
    }

    // Fix any inconsistent WAL states from old implementations
    await WalFileManager.migrateInconsistentWals(_wals);

    if (!_walReady.isCompleted) _walReady.complete();
    listener.onWalUpdated();
  }

  @override
  Future stop() async {
    _chunkingTimer?.cancel();
    _flushingTimer?.cancel();

    await _chunk();
    await _flush();

    _frames = [];
    _frameSynced = [];
  }

  @override
  Future onAudioCodecChanged(BleAudioCodec codec) async {
    // Always chunk+flush+clear to ensure clean session boundaries.
    // This is safe when frames are empty (_chunk returns immediately).
    await _chunk();
    await _flush();
    _frames = [];
    _frameSynced = [];

    _framesPerSecond = codec.getFramesPerSecond();
    _codec = codec;
  }

  @override
  void setDeviceInfo(String? deviceId, String? deviceModel) {
    _deviceId = deviceId;
    _deviceModel = deviceModel;
  }

  Future _chunk() async {
    if (_frames.isEmpty) {
      Logger.debug("Frames are empty");
      return;
    }

    var lossesThreshold = 10 * _framesPerSecond;
    var timerEnd = DateTime.now().millisecondsSinceEpoch ~/ 1000 - newFrameSyncDelaySeconds;
    var pivot = _frames.length - newFrameSyncDelaySeconds * _framesPerSecond;
    if (pivot <= 0) {
      return;
    }

    var high = pivot;
    var low = 0;
    var chunk = _frames.sublist(low, high).map((f) => f.payload).toList();
    var timerStart = timerEnd - (high - low) ~/ _framesPerSecond;
    var chunkFrameCount = high - low;

    bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      bool synced = true;
      var losses = 0;
      for (var i = low; i < high; i++) {
        if (!_frameSynced[i]) {
          losses++;
          if (losses >= lossesThreshold) {
            synced = false;
            break;
          }
        }
      }

      shouldStored = (synced == false);
    }

    if (shouldStored) {
      int syncedOffset = 0;
      for (var i = low; i < high; i++) {
        if (_frameSynced[i]) {
          syncedOffset++;
        } else {
          break;
        }
      }
      Logger.debug("${low} - ${high} - ${syncedOffset} - ${chunkFrameCount} - ${_framesPerSecond}");

      Wal wal;
      var walIdx = _wals.indexWhere(
        (w) => w.timerStart == timerStart && w.device == (_deviceId ?? "omi") && w.codec == _codec,
      );
      if (walIdx < 0) {
        wal = Wal(
          codec: _codec,
          timerStart: timerStart,
          data: chunk,
          storage: WalStorage.mem,
          status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
          device: _deviceId ?? "omi",
          deviceModel: _deviceModel ?? "Omi",
          seconds: chunkFrameCount ~/ _framesPerSecond,
          totalFrames: chunkFrameCount,
          syncedFrameOffset: syncedOffset,
        );
        _wals.add(wal);
      } else {
        wal = _wals[walIdx];
        wal.data.addAll(chunk);
        wal.storage = WalStorage.mem;
        wal.totalFrames = chunkFrameCount;
        wal.syncedFrameOffset = syncedOffset;
        wal.status = syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss;
        _wals[walIdx] = wal;
      }

      if (wal.status == WalStatus.synced) {
        listener.onWalSynced(wal);
      }
      listener.onWalUpdated();
    }

    Logger.debug("_chunk wals ${_wals.length}");

    _frames.removeRange(0, pivot);
    _frameSynced.removeRange(0, pivot);
  }

  Future _flush() async {
    Logger.debug("_flushing");
    int flushedCount = 0;
    for (var i = 0; i < _wals.length; i++) {
      final wal = _wals[i];

      if (wal.storage == WalStorage.mem) {
        String? filePath = await Wal.getFilePath(wal.getFileName());
        if (filePath == null) {
          DebugLogManager.logError('LocalWalSync flush error: Flush failed: cannot get file path', null, null, {
            'walId': wal.id,
            'timerStart': wal.timerStart,
          });
          throw Exception('Flushing to storage failed. Cannot get file path.');
        }

        List<int> data = [];
        for (int i = 0; i < wal.data.length; i++) {
          var frame = wal.data[i];

          final byteFrame = ByteData(frame.length);
          for (int j = 0; j < frame.length; j++) {
            byteFrame.setUint8(j, frame[j]);
          }
          data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
          data.addAll(byteFrame.buffer.asUint8List());
        }
        final file = File(filePath);
        await file.writeAsBytes(data);
        wal.filePath = wal.getFileName();
        wal.storage = WalStorage.disk;

        Logger.debug("_flush file ${wal.filePath}");
        flushedCount++;

        _wals[i] = wal;
      }
    }

    if (flushedCount > 0) {
      DebugLogManager.logInfo('Flushed WALs from memory to disk', {'count': flushedCount});
    }

    await _saveWalsToFile();
  }

  Future<void> _saveWalsToFile() async {
    Logger.debug('Saving WALs to file');
    await WalFileManager.saveWals(_wals);
  }

  Future<bool> _deleteWal(Wal wal) async {
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      try {
        final fullPath = await Wal.getFilePath(wal.filePath);
        if (fullPath != null) {
          final file = File(fullPath);
          if (file.existsSync()) {
            await file.delete();
          }
        }
      } catch (e) {
        Logger.debug(e.toString());
        return false;
      }
    }

    _wals.removeWhere((w) => w.id == wal.id);
    return true;
  }

  @override
  Future deleteWal(Wal wal) async {
    await _deleteWal(wal);
    listener.onWalUpdated();
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss).toList();
  }

  /// Returns unsynced WALs whose timerStart falls within [sessionStartSeconds, now].
  /// Used by the live capture screen to show inline audio safety indicators.
  List<Wal> getSessionUnsyncedWals(int sessionStartSeconds) {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    return _wals
        .where(
          (w) =>
              w.status == WalStatus.miss &&
              w.storage == WalStorage.disk &&
              w.timerStart >= sessionStartSeconds &&
              w.timerStart <= now,
        )
        .toList();
  }

  /// Mark a WAL as synced and persist the change to disk.
  Future<void> markWalSyncedAndPersist(Wal wal) async {
    wal.status = WalStatus.synced;
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  /// Force-drain all in-flight frames (including the tail buffer that _chunk() normally
  /// keeps in memory) and flush everything to disk. Call this when a capture session ends
  /// to ensure no audio is lost in memory.
  Future<void> finalizeCurrentSession() async {
    if (_frames.isEmpty) return;

    final high = _frames.length;
    if (high <= 0) return;

    var lossesThreshold = 10 * _framesPerSecond;
    var timerEnd = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    var chunk = _frames.sublist(0, high).map((f) => f.payload).toList();
    var timerStart = timerEnd - high ~/ _framesPerSecond;
    var chunkFrameCount = high;

    // Same shouldStored check as _chunk(): only store if unlimited storage enabled
    // or if significant frame loss detected (meaning WebSocket didn't deliver them).
    bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      bool synced = true;
      var losses = 0;
      for (var i = 0; i < high; i++) {
        if (!_frameSynced[i]) {
          losses++;
          if (losses >= lossesThreshold) {
            synced = false;
            break;
          }
        }
      }
      shouldStored = !synced;
    }

    if (shouldStored) {
      int syncedOffset = 0;
      for (var i = 0; i < high; i++) {
        if (_frameSynced[i]) {
          syncedOffset++;
        } else {
          break;
        }
      }

      // Use a distinct timerStart so we don't collide with WALs from _chunk().
      // This is the tail buffer that _chunk() left behind.
      _wals = List.from(_wals)
        ..add(
          Wal(
            codec: _codec,
            timerStart: timerStart,
            data: chunk,
            storage: WalStorage.mem,
            status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
            device: _deviceId ?? "omi",
            deviceModel: _deviceModel ?? "Omi",
            seconds: chunkFrameCount ~/ _framesPerSecond,
            totalFrames: chunkFrameCount,
            syncedFrameOffset: syncedOffset,
          ),
        );
    }

    _frames = [];
    _frameSynced = [];

    // Flush all in-memory WALs to disk immediately
    await _flush();
    listener.onWalUpdated();
    Logger.debug('finalizeCurrentSession: drained $chunkFrameCount frames (stored=$shouldStored), flushed to disk');
  }

  /// Stamp all session WALs with the given conversationId and persist to disk.
  /// This makes WAL→conversation linkage survive app kill.
  Future<void> stampConversationId(int sessionStartSeconds, String conversationId) async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    int stamped = 0;
    for (final wal in _wals) {
      if (wal.status == WalStatus.miss &&
          wal.timerStart >= sessionStartSeconds &&
          wal.timerStart <= now &&
          wal.conversationId == null) {
        wal.conversationId = conversationId;
        stamped++;
      }
    }
    if (stamped > 0) {
      await _saveWalsToFile();
      Logger.debug('stampConversationId: stamped $stamped WALs with conversation $conversationId');
    }
  }

  /// Returns WALs that have a conversationId but haven't been synced yet.
  /// Used for startup recovery after app kill.
  List<Wal> getOrphanedWals() {
    return _wals
        .where(
          (w) =>
              w.status == WalStatus.miss &&
              w.storage == WalStorage.disk &&
              w.conversationId != null &&
              w.retryCount < 3,
        )
        .toList();
  }

  /// Persist retry metadata (retryCount, lastRetryAt) for a WAL after failed sync attempts.
  Future<void> persistRetryMetadata(Wal wal) async {
    await _saveWalsToFile();
  }

  /// Returns the approximate duration (in seconds) of UNSYNCED audio frames
  /// still in memory. Frames already delivered via WebSocket are excluded so
  /// the "Audio Saved Locally" indicator only appears when data is at risk.
  int getInFlightSeconds() {
    if (_framesPerSecond <= 0) return 0;
    int unsyncedCount = 0;
    for (int i = 0; i < _frameSynced.length; i++) {
      if (!_frameSynced[i]) unsyncedCount++;
    }
    return unsyncedCount ~/ _framesPerSecond;
  }

  @override
  Future<List<Wal>> getAllWals() async {
    return List.from(_wals);
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllPendingWals() async {
    final pendingWals = _wals.where((w) => w.status == WalStatus.miss || w.status == WalStatus.corrupted).toList();
    for (final wal in pendingWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  @override
  void onFrameCaptured(WalFrame frame) {
    _frames.add(frame);
    _frameSynced.add(false);
  }

  @override
  void markFrameSynced(FrameSyncKey key) {
    for (int i = _frames.length - 1; i >= 0; i--) {
      if (_frames[i].syncKey == key) {
        _frameSynced[i] = true;
        break;
      }
    }
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    await _flush();
    _isCancelled = false;
    _accumulatedResponse = null;

    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.disk).toList();
    if (wals.isEmpty) {
      Logger.debug("All synced!");
      DebugLogManager.logInfo('Local upload: no files to sync');
      return null;
    }

    DebugLogManager.logEvent('local_upload_started', {'walCount': wals.length});

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    _accumulatedResponse = resp;

    int batchesCompleted = 0;
    int batchesFailed = 0;
    int corruptedCount = 0;
    int filesUploaded = 0;
    final totalFilesToUpload = wals.length;

    var steps = 3;
    for (var i = wals.length - 1; i >= 0; i -= steps) {
      if (_isCancelled) {
        Logger.debug("LocalWalSync: Upload cancelled");
        DebugLogManager.logWarning('Local upload cancelled', {
          'batchesCompleted': batchesCompleted,
          'batchesFailed': batchesFailed,
          'walsRemaining': i + 1,
        });
        // Clear isSyncing on all WALs that were marked for this batch
        for (final w in wals) {
          w.isSyncing = false;
          w.syncStartedAt = null;
          w.syncEtaSeconds = null;
        }
        await _saveWalsToFile();
        listener.onWalUpdated();
        break;
      }
      var right = i;
      var left = right - steps + 1;
      if (left < 0) {
        left = 0;
      }

      List<File> files = [];
      for (var j = left; j <= right; j++) {
        var wal = wals[j];
        Logger.debug("sync id ${wal.id} ${wal.timerStart}");
        if (wal.filePath == null) {
          Logger.debug("file path is not found. wal id ${wal.id}");
          wal.status = WalStatus.corrupted;
          corruptedCount++;
          DebugLogManager.logWarning('WAL corrupted: file path missing', {'walId': wal.id});
          continue;
        }

        final fullPath = await Wal.getFilePath(wal.filePath);
        Logger.debug("sync wal: ${wal.id} file: $fullPath");

        try {
          if (fullPath == null) {
            Logger.debug("could not construct file path for wal id ${wal.id}");
            wal.status = WalStatus.corrupted;
            corruptedCount++;
            DebugLogManager.logWarning('WAL corrupted: cannot construct path', {'walId': wal.id});
            continue;
          }

          File file = File(fullPath);
          if (!file.existsSync()) {
            Logger.debug("file $fullPath does not exist");
            wal.status = WalStatus.corrupted;
            corruptedCount++;
            DebugLogManager.logWarning('WAL corrupted: file not found on disk', {
              'walId': wal.id,
              'filePath': wal.filePath ?? '',
            });
            continue;
          }
          files.add(file);
          wal.isSyncing = true;
        } catch (e) {
          wal.status = WalStatus.corrupted;
          corruptedCount++;
          Logger.debug(e.toString());
          DebugLogManager.logError(e, null, 'WAL corrupted: unexpected error - ${e.toString()}', {'walId': wal.id});
        }
      }

      if (files.isEmpty) {
        Logger.debug("Files are empty");
        continue;
      }

      // Report file-count progress
      progress?.onWalSyncedProgress(
        filesUploaded / totalFilesToUpload,
        phase: SyncPhase.uploadingToCloud,
        currentFile: filesUploaded,
        totalFiles: totalFilesToUpload,
      );

      listener.onWalUpdated();
      try {
        var partialRes = await syncLocalFilesV2(
          files,
          onPollProgress: (jobStatus) {
            progress?.onWalSyncedProgress(
              jobStatus.totalSegments > 0 ? jobStatus.processedSegments / jobStatus.totalSegments : 0.0,
              phase: SyncPhase.processingOnServer,
              currentFile: jobStatus.processedSegments,
              totalFiles: jobStatus.totalSegments,
            );
          },
        );

        resp.newConversationIds.addAll(
          partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
        );
        resp.updatedConversationIds.addAll(
          partialRes.updatedConversationIds.where(
            (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
          ),
        );

        if (partialRes.hasPartialFailure) {
          Logger.debug(
            'WAL batch partial failure: ${partialRes.failedSegments}/${partialRes.totalSegments} segments failed',
          );
          DebugLogManager.logWarning('Local upload batch partial failure', {
            'failedSegments': partialRes.failedSegments,
            'totalSegments': partialRes.totalSegments,
            'errors': partialRes.errors.take(3).toList(),
          });
        }

        batchesCompleted++;

        for (var j = left; j <= right; j++) {
          if (j < wals.length) {
            var wal = wals[j];
            if (partialRes.hasPartialFailure) {
              // Keep WALs retryable on partial failure so failed segments get
              // another chance. Backend dedup prevents duplicate transcripts.
              wals[j].isSyncing = false;
              wals[j].syncStartedAt = null;
              wals[j].syncEtaSeconds = null;
            } else {
              wals[j].status = WalStatus.synced;
              wals[j].isSyncing = false;
              wals[j].syncStartedAt = null;
              wals[j].syncEtaSeconds = null;
              listener.onWalSynced(wal);
            }
          }
        }
        // Count actual unique synced WALs (batch ranges overlap, so don't accumulate files.length)
        filesUploaded = wals.where((w) => w.status == WalStatus.synced).length;
      } catch (e) {
        print('Local WAL sync batch failed: $e, continuing with remaining files');
        batchesFailed++;
        DebugLogManager.logError(e, null, 'Local upload batch failed: ${e.toString()}', {
          'batchIndex': (wals.length - 1 - i) ~/ steps,
          'filesInBatch': files.length,
        });
        for (var j = left; j <= right; j++) {
          if (j < wals.length) {
            wals[j].isSyncing = false;
            wals[j].syncStartedAt = null;
            wals[j].syncEtaSeconds = null;
          }
        }
      }

      await _saveWalsToFile();
      listener.onWalUpdated();
    }

    DebugLogManager.logEvent('local_upload_finished', {
      'batchesCompleted': batchesCompleted,
      'batchesFailed': batchesFailed,
      'corrupted': corruptedCount,
      'newConversations': resp.newConversationIds.length,
      'updatedConversations': resp.updatedConversationIds.length,
    });

    progress?.onWalSyncedProgress(1.0);
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    await _flush();

    var walToSync = _wals.where((w) => w == wal).toList().first;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    DebugLogManager.logInfo('Single WAL upload started', {
      'walId': wal.id,
      'seconds': wal.seconds,
      'codec': wal.codec.toString(),
    });

    late File walFile;
    if (wal.filePath == null) {
      Logger.debug("file path is not found. wal id ${wal.id}");
      wal.status = WalStatus.corrupted;
      DebugLogManager.logWarning('Single WAL corrupted: file path missing', {'walId': wal.id});
    }
    try {
      final fullPath = await Wal.getFilePath(wal.filePath);
      if (fullPath == null) {
        Logger.debug("could not construct file path for wal id ${wal.id}");
        wal.status = WalStatus.corrupted;
        DebugLogManager.logWarning('Single WAL corrupted: cannot construct path', {'walId': wal.id});
      } else {
        File file = File(fullPath);
        if (!file.existsSync()) {
          Logger.debug("file $fullPath does not exist");
          wal.status = WalStatus.corrupted;
          DebugLogManager.logWarning('Single WAL corrupted: file not found', {'walId': wal.id});
        } else {
          walFile = file;
          wal.isSyncing = true;
        }
      }
    } catch (e) {
      wal.status = WalStatus.corrupted;
      print(e.toString());
      DebugLogManager.logError(e, null, 'Single WAL corrupted: unexpected error - ${e.toString()}', {'walId': wal.id});
    }

    listener.onWalUpdated();
    try {
      var partialRes = await syncLocalFilesV2(
        [walFile],
        onPollProgress: (jobStatus) {
          progress?.onWalSyncedProgress(
            jobStatus.totalSegments > 0 ? jobStatus.processedSegments / jobStatus.totalSegments : 0.0,
            phase: SyncPhase.processingOnServer,
            currentFile: jobStatus.processedSegments,
            totalFiles: jobStatus.totalSegments,
          );
        },
      );

      resp.newConversationIds.addAll(
        partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
      );
      resp.updatedConversationIds.addAll(
        partialRes.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );

      if (partialRes.hasPartialFailure) {
        Logger.debug(
          'Single WAL partial failure: ${partialRes.failedSegments}/${partialRes.totalSegments} segments failed',
        );
        DebugLogManager.logWarning('Single WAL upload partial failure', {
          'walId': wal.id,
          'failedSegments': partialRes.failedSegments,
          'totalSegments': partialRes.totalSegments,
          'errors': partialRes.errors.take(3).toList(),
        });
      }

      if (partialRes.hasPartialFailure) {
        // Keep WAL retryable so failed segments get another chance
        walToSync.isSyncing = false;
        walToSync.syncStartedAt = null;
        walToSync.syncEtaSeconds = null;
      } else {
        walToSync.status = WalStatus.synced;
        walToSync.isSyncing = false;
        walToSync.syncStartedAt = null;
        walToSync.syncEtaSeconds = null;
        DebugLogManager.logInfo('Single WAL upload succeeded', {'walId': wal.id});
        listener.onWalSynced(wal);
      }
    } catch (e) {
      Logger.debug('Single WAL sync failed: $e');
      DebugLogManager.logError(e, null, 'Single WAL upload failed: ${e.toString()}', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      rethrow;
    }

    await _saveWalsToFile();
    listener.onWalUpdated();

    progress?.onWalSyncedProgress(1.0);
    return resp;
  }
}
