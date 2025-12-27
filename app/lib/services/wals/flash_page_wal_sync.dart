import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/limitless_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:path_provider/path_provider.dart';

class FlashPageWalSyncImpl implements FlashPageWalSync {
  static const int pagesPerChunk = 25;
  static const String _pendingFilesKey = 'flash_page_pending_uploads';
  static const Duration _persistBatchDuration = Duration(seconds: 90);

  List<Wal> _wals = const [];
  BtDevice? _device;

  StreamSubscription? _pageStream;

  int _oldestPage = 0;
  int _newestPage = 0;
  int _currentSession = 0;

  bool _isSyncing = false;
  @override
  bool get isSyncing => _isSyncing;

  bool _isUploading = false;
  @override
  bool get isUploading => _isUploading;

  IWalSyncListener listener;

  FlashPageWalSyncImpl(this.listener);

  @override
  void cancelSync() {
    // Flash page sync doesn't support cancellation yet
  }

  List<String> _getPendingFiles() {
    return SharedPreferencesUtil().getStringList(_pendingFilesKey);
  }

  void _savePendingFiles(List<String> files) {
    SharedPreferencesUtil().saveStringList(_pendingFilesKey, files);
  }

  void _addPendingFile(String filePath) {
    final files = List<String>.from(_getPendingFiles());
    if (!files.contains(filePath)) {
      files.add(filePath);
      _savePendingFiles(files);
    }
  }

  void _removePendingFile(String filePath) {
    final files = List<String>.from(_getPendingFiles());
    files.remove(filePath);
    _savePendingFiles(files);
  }

  @override
  Future<SyncLocalFilesResponse> uploadOrphanedFiles() async {
    final pendingFiles = _getPendingFiles();
    if (pendingFiles.isEmpty) {
      return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    }

    _isUploading = true;
    listener.onWalUpdated();
    debugPrint("FlashPageSync: Uploading ${pendingFiles.length} orphaned files with sequential batches");

    try {
      final result = await _uploadAllPendingFilesSequential();
      return result;
    } finally {
      _isUploading = false;
      listener.onWalUpdated();
    }
  }

  @override
  bool get hasOrphanedFiles => _getPendingFiles().isNotEmpty;

  @override
  int get orphanedFilesCount => _getPendingFiles().length;

  Future<Map<String, int>?> _getStorageStatus(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return null;

    try {
      final limitlessConnection = connection as LimitlessDeviceConnection;
      return await limitlessConnection.getStorageStatus();
    } catch (e) {
      debugPrint('FlashPageSync: Not a Limitless device or getStorageStatus not available: $e');
      return null;
    }
  }

  Future<void> _acknowledgeProcessedData(String deviceId, int upToIndex) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection is LimitlessDeviceConnection) {
      try {
        await connection.acknowledgeProcessedData(upToIndex);
      } catch (e) {
        debugPrint('FlashPageSync: Could not acknowledge processed data: $e');
      }
    }
  }

  Future<void> _enableRealTimeMode(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;

    if (connection is LimitlessDeviceConnection) {
      try {
        await connection.enableRealTimeMode();
      } catch (e) {
        debugPrint('FlashPageSync: Could not enable real-time mode: $e');
      }
    }
  }

  @override
  Future deleteWal(Wal wal) async {
    _wals.removeWhere((w) => w.id == wal.id);

    if (_device != null && wal.status == WalStatus.synced) {
      await _acknowledgeProcessedData(_device!.id, wal.storageTotalBytes);
    }

    listener.onWalUpdated();
  }

  Future<List<Wal>> _getMissingWals() async {
    if (_device == null) return [];

    if (_device!.type != DeviceType.limitless) return [];

    String deviceId = _device!.id;
    List<Wal> wals = [];

    var storageStatus = await _getStorageStatus(deviceId);
    if (storageStatus == null || storageStatus.isEmpty) return [];

    _oldestPage = storageStatus['oldest_flash_page'] ?? 0;
    _newestPage = storageStatus['newest_flash_page'] ?? 0;
    _currentSession = storageStatus['current_storage_session'] ?? 0;

    int pageCount = _newestPage - _oldestPage + 1;
    if (pageCount <= 0) return [];

    int estimatedSeconds = pageCount * 2;

    if (pageCount > 30) {
      int timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - estimatedSeconds;

      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      var pd = await _device!.getDeviceInfo(connection);
      String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Limitless";

      wals.add(Wal(
        codec: BleAudioCodec.opus,
        timerStart: timerStart,
        status: WalStatus.miss,
        storage: WalStorage.flashPage,
        seconds: estimatedSeconds,
        storageOffset: _oldestPage,
        storageTotalBytes: _newestPage,
        fileNum: _currentSession,
        device: _device!.id,
        deviceModel: deviceModel,
        totalFrames: pageCount * framesPerFlashPage,
        syncedFrameOffset: 0,
      ));
    }

    return wals;
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.flashPage).toList();
  }

  @override
  Future start() async {
    _wals = await _getMissingWals();
    listener.onWalUpdated();

    if (hasOrphanedFiles) {
      uploadOrphanedFiles();
    }
  }

  @override
  Future stop() async {
    _wals = [];
    await _pageStream?.cancel();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.flashPage).toList();
    if (wals.isEmpty) {
      debugPrint("FlashPageSync: All synced!");
      return null;
    }

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    for (var i = wals.length - 1; i >= 0; i--) {
      var wal = wals[i];

      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
      listener.onWalUpdated();

      var partialRes = await _syncWal(wal, progress);
      if (partialRes != null) {
        resp.newConversationIds
            .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));
      }

      wal.status = WalStatus.synced;
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      listener.onWalUpdated();
    }

    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    var walToSync = _wals.where((w) => w == wal).toList().first;

    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    listener.onWalUpdated();

    var resp = await _syncWal(walToSync, progress);

    walToSync.status = WalStatus.synced;
    walToSync.isSyncing = false;
    walToSync.syncStartedAt = null;
    walToSync.syncEtaSeconds = null;

    listener.onWalUpdated();
    return resp;
  }

  Future<SyncLocalFilesResponse> _uploadAllPendingFilesSequential({bool continuous = false}) async {
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    debugPrint("FlashPageSync: Starting sequential batch upload${continuous ? ' (continuous mode)' : ''}");

    const batchSize = 2;
    int totalBatchesProcessed = 0;

    while (true) {
      final pendingFiles = _getPendingFiles();
      if (pendingFiles.isEmpty) {
        if (continuous && _isSyncing) {
          await Future.delayed(const Duration(seconds: 3));
          continue;
        }
        break;
      }

      final sortedFiles = List<String>.from(pendingFiles);
      sortedFiles.sort((a, b) {
        final tsA = _extractTimestampFromFilename(a);
        final tsB = _extractTimestampFromFilename(b);
        return tsA.compareTo(tsB);
      });

      final batchPaths = sortedFiles.take(batchSize).toList();
      totalBatchesProcessed++;

      debugPrint(
          "FlashPageSync: Uploading batch #$totalBatchesProcessed (${batchPaths.length} files, ${pendingFiles.length - batchPaths.length} remaining)");

      final result = await _uploadBatch(batchPaths);

      final batchResp = result['response'] as SyncLocalFilesResponse?;
      if (batchResp != null) {
        resp.newConversationIds
            .addAll(batchResp.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(batchResp.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));
      }

      await Future.delayed(const Duration(seconds: 1));
    }

    debugPrint(
        "FlashPageSync: Upload complete. Processed $totalBatchesProcessed batches. Total conversations: ${resp.newConversationIds.length} new, ${resp.updatedConversationIds.length} updated. Remaining files: ${_getPendingFiles().length}");
    return resp;
  }

  Future<Map<String, dynamic>> _uploadBatch(List<String> batchPaths) async {
    final batchFiles = <File>[];
    final validPaths = <String>[];

    for (final filePath in batchPaths) {
      final file = File(filePath);
      if (await file.exists()) {
        batchFiles.add(file);
        validPaths.add(filePath);
      } else {
        _removePendingFile(filePath);
      }
    }

    if (batchFiles.isEmpty) {
      return {'response': null, 'paths': <String>[]};
    }

    try {
      debugPrint("FlashPageSync: Uploading batch of ${batchFiles.length} files");
      final partialResp = await syncLocalFiles(batchFiles);

      for (final filePath in validPaths) {
        try {
          await File(filePath).delete();
          _removePendingFile(filePath);
        } catch (e) {
          debugPrint("FlashPageSync: Failed to delete file $filePath: $e");
        }
      }

      return {'response': partialResp, 'paths': validPaths};
    } catch (e) {
      debugPrint("FlashPageSync: Failed to upload batch: $e");
      return {'response': null, 'paths': <String>[]};
    }
  }

  Future<SyncLocalFilesResponse?> _syncWal(Wal wal, IWalSyncProgressListener? progress) async {
    if (_device == null) return null;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    String deviceId = _device!.id;

    try {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        debugPrint("FlashPageSync: Could not get connection");
        return null;
      }

      final limitlessConnection = connection as LimitlessDeviceConnection;
      limitlessConnection.clearBuffer();
      await limitlessConnection.enableBatchMode();
      debugPrint("FlashPageSync: Batch mode enabled");

      _isSyncing = true;
      listener.onWalUpdated();

      int totalPages = wal.storageTotalBytes - wal.storageOffset + 1;
      int emptyExtractions = 0;
      const maxEmptyExtractions = 60;
      int? lastProcessedIndex;

      List<List<int>> accumulatedFrames = [];
      int? batchMinTimestamp;
      DateTime lastSaveTime = DateTime.now();
      int filesSaved = 0;

      bool syncComplete = false;

      bool uploadStarted = false;
      Future<SyncLocalFilesResponse>? backgroundUpload;

      while (!syncComplete) {
        final pageData = limitlessConnection.extractFramesWithSessionInfo();
        bool shouldSave = false;

        List<List<int>>? pendingFrames;
        int? pendingTimestamp;

        if (pageData != null) {
          emptyExtractions = 0;

          final opusFrames = pageData['opus_frames'] as List<List<int>>? ?? [];
          final timestampMs = pageData['timestamp_ms'] as int? ?? DateTime.now().millisecondsSinceEpoch;
          final maxIndex = pageData['max_index'] as int?;
          final didStartSession =
              (pageData['did_start_session'] as bool? ?? false) || (pageData['did_start_recording'] as bool? ?? false);
          final didStopSession =
              (pageData['did_stop_session'] as bool? ?? false) || (pageData['did_stop_recording'] as bool? ?? false);

          if (maxIndex != null && (lastProcessedIndex == null || maxIndex > lastProcessedIndex)) {
            lastProcessedIndex = maxIndex;
          }

          if (opusFrames.isNotEmpty) {
            const sessionGapThresholdMs = 120000;
            if (batchMinTimestamp != null && accumulatedFrames.isNotEmpty) {
              final gap = (timestampMs - batchMinTimestamp).abs();
              if (gap > sessionGapThresholdMs) {
                shouldSave = true;
                pendingFrames = opusFrames;
                pendingTimestamp = timestampMs;
              }
            }

            if (!shouldSave && didStartSession && accumulatedFrames.isNotEmpty) {
              shouldSave = true;
              pendingFrames = opusFrames;
              pendingTimestamp = timestampMs;
            }

            if (!shouldSave) {
              if (batchMinTimestamp == null || timestampMs < batchMinTimestamp) {
                batchMinTimestamp = timestampMs;
              }
              accumulatedFrames.addAll(opusFrames);
            }

            if (didStopSession && accumulatedFrames.isNotEmpty) {
              shouldSave = true;
            }
          }
        } else {
          emptyExtractions++;
        }

        if (!shouldSave && accumulatedFrames.isNotEmpty) {
          if (DateTime.now().difference(lastSaveTime) >= _persistBatchDuration) {
            shouldSave = true;
          }
        }

        if (shouldSave && accumulatedFrames.isNotEmpty) {
          final filePath = await _saveBatchToFile(
            accumulatedFrames,
            batchMinTimestamp ?? DateTime.now().millisecondsSinceEpoch,
          );

          if (filePath != null) {
            filesSaved++;
            debugPrint(
                "FlashPageSync: Saved batch #$filesSaved to disk (${accumulatedFrames.length} frames, ts=$batchMinTimestamp)");
            progress?.onWalSyncedProgress((filesSaved / (totalPages / 50)).clamp(0.0, 0.8));

            if (lastProcessedIndex != null) {
              try {
                await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
                debugPrint("FlashPageSync: Incremental ACK sent for page $lastProcessedIndex");
              } catch (e) {
                debugPrint("FlashPageSync: Incremental ACK failed: $e");
              }
            }

            if (!uploadStarted && filesSaved >= 2) {
              uploadStarted = true;
              _isUploading = true;
              listener.onWalUpdated();
              debugPrint("FlashPageSync: Starting background upload while syncing continues");
              backgroundUpload = _uploadAllPendingFilesSequential(continuous: true);
            }
          }

          accumulatedFrames.clear();
          batchMinTimestamp = null;
          lastSaveTime = DateTime.now();

          if (pendingFrames != null && pendingFrames.isNotEmpty) {
            accumulatedFrames.addAll(pendingFrames);
            batchMinTimestamp = pendingTimestamp;
          }
        }

        if (emptyExtractions >= maxEmptyExtractions) {
          debugPrint("FlashPageSync: No more data from device");
          syncComplete = true;
        }

        await Future.delayed(const Duration(milliseconds: 500));
      }

      if (accumulatedFrames.isNotEmpty) {
        final filePath = await _saveBatchToFile(
          accumulatedFrames,
          batchMinTimestamp ?? DateTime.now().millisecondsSinceEpoch,
        );
        if (filePath != null) {
          filesSaved++;
          debugPrint("FlashPageSync: Saved final batch #$filesSaved to disk");

          if (lastProcessedIndex != null) {
            try {
              await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
              debugPrint("FlashPageSync: Final ACK sent for page $lastProcessedIndex");
            } catch (e) {
              debugPrint("FlashPageSync: Final ACK failed: $e");
            }
          }
        }
      }

      _isSyncing = false;
      listener.onWalUpdated();

      if (lastProcessedIndex != null) {
        try {
          await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
          debugPrint("FlashPageSync: Sent final ACK for index $lastProcessedIndex before switching to real-time");
        } catch (e) {
          debugPrint("FlashPageSync: Final cleanup ACK failed: $e");
        }
      }

      await limitlessConnection.enableRealTimeMode();

      if (backgroundUpload != null) {
        debugPrint("FlashPageSync: Waiting for background upload to complete");
        final uploadResult = await backgroundUpload;
        resp.newConversationIds.addAll(uploadResult.newConversationIds);
        resp.updatedConversationIds.addAll(uploadResult.updatedConversationIds);
      }

      final remainingFiles = _getPendingFiles();
      if (remainingFiles.isNotEmpty) {
        if (!uploadStarted) {
          _isUploading = true;
          listener.onWalUpdated();
        }
        debugPrint("FlashPageSync: Uploading ${remainingFiles.length} remaining files");
        final uploadResult = await _uploadAllPendingFilesSequential();
        resp.newConversationIds.addAll(uploadResult.newConversationIds);
        resp.updatedConversationIds.addAll(uploadResult.updatedConversationIds);
      }

      _isUploading = false;
      listener.onWalUpdated();

      debugPrint("FlashPageSync: Completed. $filesSaved files saved, uploads processed");
      progress?.onWalSyncedProgress(1.0);
    } catch (e) {
      debugPrint("FlashPageSync: Error: $e");
      _isSyncing = false;
      _isUploading = false;
      listener.onWalUpdated();
      try {
        await _enableRealTimeMode(deviceId);
      } catch (_) {}
    }

    return resp;
  }

  Future<String?> _saveBatchToFile(List<List<int>> frames, int timestampMs) async {
    if (frames.isEmpty) return null;

    try {
      final random = DateTime.now().microsecondsSinceEpoch % 10000;
      final tempDir = await getApplicationDocumentsDirectory();
      final fileName = 'audio_limitless_opus_16000_1_fs320_r${random}_$timestampMs.bin';
      final filePath = '${tempDir.path}/$fileName';

      final file = File(filePath);
      final sink = file.openWrite();
      for (final frame in frames) {
        sink.add([
          frame.length & 0xFF,
          (frame.length >> 8) & 0xFF,
          (frame.length >> 16) & 0xFF,
          (frame.length >> 24) & 0xFF,
        ]);
        sink.add(frame);
      }
      await sink.close();

      _addPendingFile(filePath);

      return filePath;
    } catch (e) {
      debugPrint("FlashPageSync: Save batch error: $e");
      return null;
    }
  }

  int _extractTimestampFromFilename(String filePath) {
    try {
      final fileName = filePath.split('/').last;
      final parts = fileName.split('_');
      if (parts.isNotEmpty) {
        final lastPart = parts.last.replaceAll('.bin', '');
        return int.tryParse(lastPart) ?? 0;
      }
    } catch (e) {
      debugPrint("FlashPageSync: Failed to extract timestamp from $filePath: $e");
    }
    return 0;
  }

  @override
  void setDevice(BtDevice? device) async {
    _device = device;
    if (device != null && device.type == DeviceType.limitless) {
      _wals = await _getMissingWals();
    } else {
      _wals = [];
    }
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      await deleteWal(wal);
    }
  }
}
