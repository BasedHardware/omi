import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/limitless_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/logger.dart';

class FlashPageWalSyncImpl implements FlashPageWalSync {
  static const int pagesPerChunk = 25;
  static const Duration _persistBatchDuration = Duration(seconds: 90);

  List<Wal> _wals = const [];
  BtDevice? _device;
  LocalWalSync? _localSync;

  StreamSubscription? _pageStream;

  int _oldestPage = 0;
  int _newestPage = 0;
  int _currentSession = 0;

  bool _isSyncing = false;
  bool _cancelRequested = false;
  String? _currentDeviceId;

  @override
  bool get isSyncing => _isSyncing;

  IWalSyncListener listener;

  FlashPageWalSyncImpl(this.listener);

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void cancelSync() {
    if (_isSyncing) {
      Logger.debug("FlashPageSync: Cancel requested");
      _cancelRequested = true;
    }
  }

  Future<Map<String, int>?> _getStorageStatus(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return null;

    try {
      final limitlessConnection = connection as LimitlessDeviceConnection;
      return await limitlessConnection.getStorageStatus();
    } catch (e) {
      Logger.debug('FlashPageSync: Not a Limitless device or getStorageStatus not available: $e');
      return null;
    }
  }

  Future<void> _acknowledgeProcessedData(String deviceId, int upToIndex) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection is LimitlessDeviceConnection) {
      try {
        await connection.acknowledgeProcessedData(upToIndex);
      } catch (e) {
        Logger.debug('FlashPageSync: Could not acknowledge processed data: $e');
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
        Logger.debug('FlashPageSync: Could not enable real-time mode: $e');
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

    // Each flash page contains ~1.4 seconds of audio
    int estimatedSeconds = (pageCount * secondsPerFlashPage).round();

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
  }

  @override
  Future stop() async {
    _wals = [];
    await _pageStream?.cancel();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.flashPage).toList();
    if (wals.isEmpty) {
      Logger.debug("FlashPageSync: All downloaded!");
      return null;
    }

    for (var i = wals.length - 1; i >= 0; i--) {
      var wal = wals[i];

      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
      wal.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();

      final completed = await _syncWal(wal, progress);

      if (completed) {
        wal.status = WalStatus.synced;
      }
      // If cancelled, status remains 'miss' so user can resume later

      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      listener.onWalUpdated();

      // If cancelled, stop processing remaining WALs
      if (!completed && _cancelRequested) {
        Logger.debug("FlashPageSync: Stopping syncAll due to cancellation");
        break;
      }
    }

    return null;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    var walToSync = _wals.where((w) => w == wal).toList().first;

    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    listener.onWalUpdated();

    final completed = await _syncWal(walToSync, progress);

    if (completed) {
      walToSync.status = WalStatus.synced;
    }
    // If cancelled, status remains 'miss' so user can resume later

    walToSync.isSyncing = false;
    walToSync.syncStartedAt = null;
    walToSync.syncEtaSeconds = null;
    walToSync.syncSpeedKBps = null;

    listener.onWalUpdated();
    return null;
  }

  /// Downloads flash page data from device and registers chunks with LocalWalSync.
  /// Returns true if sync completed successfully, false if cancelled or failed.
  Future<bool> _syncWal(Wal wal, IWalSyncProgressListener? progress) async {
    if (_device == null) return false;

    String deviceId = _device!.id;
    _currentDeviceId = deviceId;
    _cancelRequested = false;

    try {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        Logger.debug("FlashPageSync: Could not get connection");
        return false;
      }

      final limitlessConnection = connection as LimitlessDeviceConnection;
      limitlessConnection.clearBuffer();
      await limitlessConnection.enableBatchMode();
      Logger.debug("FlashPageSync: Batch mode enabled");

      _isSyncing = true;
      listener.onWalUpdated();

      final int startPage = wal.storageOffset;
      final int endPage = wal.storageTotalBytes;
      final int totalPages = endPage - startPage + 1;
      int emptyExtractions = 0;
      const maxEmptyExtractions = 60;
      int? lastProcessedIndex;

      final DateTime syncStartTime = DateTime.now();

      List<List<int>> accumulatedFrames = [];
      int? batchMinTimestamp;
      DateTime lastSaveTime = DateTime.now();
      int filesSaved = 0;

      bool syncComplete = false;

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

          if (maxIndex != null && (lastProcessedIndex == null || maxIndex > lastProcessedIndex)) {
            lastProcessedIndex = maxIndex;

            final pagesProcessed = lastProcessedIndex - startPage;
            final progressPercent = totalPages > 0 ? pagesProcessed / totalPages : 0.0;

            // Calculate speed (pages per second) and ETA
            final elapsedSeconds = DateTime.now().difference(syncStartTime).inMilliseconds / 1000.0;
            double pagesPerSecond = 0;
            if (elapsedSeconds > 0) {
              pagesPerSecond = pagesProcessed / elapsedSeconds;
            }

            // Update WAL with sync progress info
            wal.syncedFrameOffset = pagesProcessed;
            if (pagesPerSecond > 0) {
              final pagesRemaining = endPage - lastProcessedIndex;
              wal.syncEtaSeconds = (pagesRemaining / pagesPerSecond).round();
              // Convert pages/sec to approx KB/s (each page ~160 bytes of opus data)
              wal.syncSpeedKBps = pagesPerSecond * 0.16;
            }

            progress?.onWalSyncedProgress(progressPercent.clamp(0.0, 0.95), speedKBps: wal.syncSpeedKBps);
            listener.onWalUpdated();
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

            if (!shouldSave) {
              if (batchMinTimestamp == null || timestampMs < batchMinTimestamp) {
                batchMinTimestamp = timestampMs;
              }
              accumulatedFrames.addAll(opusFrames);
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
            wal,
          );

          if (filePath != null) {
            filesSaved++;
            Logger.debug(
                "FlashPageSync: Saved batch #$filesSaved to disk (${accumulatedFrames.length} frames, ts=$batchMinTimestamp)");

            if (lastProcessedIndex != null) {
              try {
                await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
                Logger.debug("FlashPageSync: Incremental ACK sent for page $lastProcessedIndex");
              } catch (e) {
                Logger.debug("FlashPageSync: Incremental ACK failed: $e");
              }
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
          Logger.debug("FlashPageSync: No more data from device");
          syncComplete = true;
        }

        // Check for cancellation request
        if (_cancelRequested) {
          Logger.debug("FlashPageSync: Cancellation requested, saving progress and stopping");

          // Save any accumulated frames before cancelling
          if (accumulatedFrames.isNotEmpty) {
            final filePath = await _saveBatchToFile(
              accumulatedFrames,
              batchMinTimestamp ?? DateTime.now().millisecondsSinceEpoch,
              wal,
            );
            if (filePath != null) {
              filesSaved++;
              Logger.debug("FlashPageSync: Saved batch before cancel #$filesSaved to disk");
            }
            accumulatedFrames.clear();
          }

          // Send ACK for processed data
          if (lastProcessedIndex != null) {
            try {
              await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
              Logger.debug("FlashPageSync: Cancel ACK sent for page $lastProcessedIndex");

              // Update WAL to reflect remaining pages (for next sync attempt)
              wal.storageOffset = lastProcessedIndex + 1;
              final remainingPages = endPage - lastProcessedIndex;
              wal.seconds = (remainingPages * secondsPerFlashPage).round();
              Logger.debug(
                  "FlashPageSync: Updated WAL - new start page: ${wal.storageOffset}, remaining: $remainingPages pages");
            } catch (e) {
              Logger.debug("FlashPageSync: Cancel ACK failed: $e");
            }
          }

          // Switch back to real-time mode
          _isSyncing = false;
          _cancelRequested = false;
          wal.syncEtaSeconds = null;
          wal.syncSpeedKBps = null;
          listener.onWalUpdated();

          await limitlessConnection.enableRealTimeMode();
          Logger.debug("FlashPageSync: Cancelled. $filesSaved files saved before cancellation");
          return false; // Cancelled, not completed
        }

        await Future.delayed(const Duration(milliseconds: 500));
      }

      if (accumulatedFrames.isNotEmpty) {
        final filePath = await _saveBatchToFile(
          accumulatedFrames,
          batchMinTimestamp ?? DateTime.now().millisecondsSinceEpoch,
          wal,
        );
        if (filePath != null) {
          filesSaved++;
          Logger.debug("FlashPageSync: Saved final batch #$filesSaved to disk");

          if (lastProcessedIndex != null) {
            try {
              await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
              Logger.debug("FlashPageSync: Final ACK sent for page $lastProcessedIndex");
            } catch (e) {
              Logger.debug("FlashPageSync: Final ACK failed: $e");
            }
          }
        }
      }

      _isSyncing = false;

      // Clear sync progress info
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;

      listener.onWalUpdated();

      // Final ACK before switching to real-time mode
      if (lastProcessedIndex != null) {
        try {
          await limitlessConnection.acknowledgeProcessedData(lastProcessedIndex);
          Logger.debug("FlashPageSync: Sent final ACK for index $lastProcessedIndex before switching to real-time");
        } catch (e) {
          Logger.debug("FlashPageSync: Final cleanup ACK failed: $e");
        }
      }

      await limitlessConnection.enableRealTimeMode();

      Logger.debug("FlashPageSync: Download complete. $filesSaved files saved and registered with LocalWalSync");
      progress?.onWalSyncedProgress(1.0);
      return true; // Completed successfully
    } catch (e) {
      Logger.debug("FlashPageSync: Error: $e");
      _isSyncing = false;

      // Clear sync progress info on error
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;

      listener.onWalUpdated();
      try {
        await _enableRealTimeMode(deviceId);
      } catch (_) {}
      return false; // Failed
    }
  }

  /// Saves a batch of frames to disk and registers with LocalWalSync for later upload.
  Future<String?> _saveBatchToFile(List<List<int>> frames, int timestampMs, Wal sourceWal) async {
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

      await _registerChunkWithLocalSync(fileName, timestampMs, frames.length, sourceWal);

      return filePath;
    } catch (e) {
      Logger.debug("FlashPageSync: Save batch error: $e");
      return null;
    }
  }

  Future<void> _registerChunkWithLocalSync(String fileName, int timestampMs, int frameCount, Wal sourceWal) async {
    if (_localSync == null) {
      Logger.debug("FlashPageSync: WARNING - Cannot register chunk, LocalWalSync not available");
      return;
    }

    int seconds = (frameCount / 50).ceil();
    if (seconds < 1) seconds = 1;

    Wal localWal = Wal(
      codec: BleAudioCodec.opus,
      channel: 1,
      sampleRate: 16000,
      timerStart: timestampMs ~/ 1000,
      filePath: fileName,
      storage: WalStorage.disk,
      status: WalStatus.miss,
      device: sourceWal.device,
      deviceModel: sourceWal.deviceModel ?? "Limitless",
      seconds: seconds,
      totalFrames: frameCount,
      syncedFrameOffset: 0,
      originalStorage: WalStorage.flashPage,
    );

    await _localSync!.addExternalWal(localWal);
    Logger.debug("FlashPageSync: Registered chunk (ts: $timestampMs, ${seconds}s) with LocalWalSync");
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
