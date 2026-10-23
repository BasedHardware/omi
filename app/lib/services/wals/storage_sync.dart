import 'package:omi/services/wals/local_wal_sync.dart';
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Offline storage sync for new multi-file firmware protocol (CMD_LIST_FILES 0x10,
/// CMD_READ_FILE 0x11, CMD_DELETE_FILE 0x12). Downloads individual files from
/// device LittleFS storage to phone, then hands them to LocalWalSync for upload.
///
/// Closely follows the proven BLE sync pattern from PR #5905's sdcard_wal_sync changes.
class StorageSyncImpl implements StorageSync {
  List<Wal> _wals = [];
  BtDevice? _device;

  StreamSubscription? _storageStream;
  Completer<bool>? _activeTransfer;
  String? _activeSyncDeviceId;
  DeviceConnection? _activeSyncConnection;
  int? _activeSyncEpoch;
  bool _firmwareStopRequested = false;

  IWalSyncListener listener;
  LocalWalSync? _localSync;

  bool _isCancelled = false;
  bool _isSyncing = false;
  @override
  bool get isSyncing => _isSyncing;

  int _totalBytesDownloaded = 0;
  DateTime? _downloadStartTime;
  double _currentSpeedKBps = 0.0;
  @override
  double get currentSpeedKBps => _currentSpeedKBps;

  StorageSyncImpl(this.listener);

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  @visibleForTesting
  set testDevice(BtDevice? device) => _device = device;

  DeviceConnection? _testConnection;

  @visibleForTesting
  set testConnection(DeviceConnection? connection) => _testConnection = connection;

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void setDevice(BtDevice? device) {
    _device = device;
  }

  @override
  void cancelSync() {
    if (_isSyncing) {
      _isCancelled = true;
      Logger.debug("StorageSync: Cancel requested");

      final storageSub = _storageStream;
      if (storageSub != null) {
        unawaited(storageSub.cancel());
      }
      // The cancelled subscription delivers no more packets, so the data
      // callback never sees _isCancelled. End the file transfer here, or it
      // only ends at its 10-minute timeout.
      final transfer = _activeTransfer;
      if (transfer != null && !transfer.isCompleted) {
        transfer.complete(false);
      }
      unawaited(_requestFirmwareStopSync());
    }
  }

  Future<void> _requestFirmwareStopSync() async {
    if (_firmwareStopRequested) return;
    _firmwareStopRequested = true;

    final deviceId = _activeSyncDeviceId ?? _device?.id;
    if (deviceId == null || deviceId.isEmpty) return;

    try {
      var connection = _activeSyncConnection ?? _testConnection;
      if (connection != null && _activeSyncEpoch != null) {
        try {
          if (connection.connectionEpoch != _activeSyncEpoch) connection = null;
        } catch (_) {}
      }
      connection ??= await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) return;
      await connection.stopStorageSync();
      Logger.debug("StorageSync: STOP command sent to firmware");
    } catch (e) {
      Logger.debug("StorageSync: Failed to send STOP command: $e");
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
    _activeSyncDeviceId = null;
    _activeSyncConnection = null;
    _activeSyncEpoch = null;
    _firmwareStopRequested = false;
    _totalBytesDownloaded = 0;
    _downloadStartTime = null;
    _currentSpeedKBps = 0.0;
  }

  void _updateSpeed(int newBytes) {
    _totalBytesDownloaded += newBytes;
    if (_downloadStartTime != null) {
      final elapsedSeconds = DateTime.now().difference(_downloadStartTime!).inMilliseconds / 1000.0;
      if (elapsedSeconds > 0.5) {
        _currentSpeedKBps = (_totalBytesDownloaded / 1024.0) / elapsedSeconds;
      }
    }
  }

  /// Check if the connected device has files to sync using the new protocol.
  /// Returns false for old firmware (getStorageFileStats returns null).
  @override
  Future<bool> hasFilesToSync() async {
    if (_device == null) {
      Logger.debug('StorageSync.hasFilesToSync: _device is null');
      return false;
    }
    try {
      var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) {
        Logger.debug('StorageSync.hasFilesToSync: connection is null');
        return false;
      }
      final status = await connection.getStorageFileStats();
      final result = status != null && status.fileCount > 0;
      Logger.debug('StorageSync.hasFilesToSync: status=$status result=$result');
      return result;
    } catch (e) {
      Logger.debug('StorageSync.hasFilesToSync: error: $e');
      return false;
    }
  }

  /// Returns cached WAL list from memory. Safe to call during sync — never touches BLE.
  /// Call refreshWalsFromDevice() first to populate the list via BLE.
  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
  }

  /// Whether [wal] is one of the device files this sync listed. Its recordings
  /// share [WalStorage.sdcard] with the legacy SD card sync, so per-recording
  /// actions use this to reach the right sync.
  bool owns(Wal wal) => _wals.any((w) => identical(w, wal));

  /// Discover files on device via BLE. Must be called BEFORE syncAll() to populate _wals.
  /// Sends STOP command and subscribes to data characteristic — never call during an active sync.
  Future<void> refreshWalsFromDevice() async {
    if (_device == null) return;
    if (_isSyncing) {
      Logger.debug('StorageSync.refreshWalsFromDevice: skipping — sync in progress');
      return;
    }

    try {
      var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) return;

      final status = await connection.getStorageFileStats();
      Logger.debug('StorageSync.refreshWalsFromDevice: status=$status');
      if (status == null || status.fileCount == 0) {
        _wals = [];
        return;
      }

      // Stop any active auto-sync before listing (per PR #5905 pattern)
      await connection.stopStorageSync();
      await Future.delayed(const Duration(milliseconds: 500));

      // Retry up to 3 times (per PR #5905 pattern)
      List<StorageFileInfo> files = [];
      for (int attempt = 0; attempt < 3 && files.isEmpty; attempt++) {
        files = await connection.listStorageFiles();
        Logger.debug(
          'StorageSync.refreshWalsFromDevice: listFiles attempt ${attempt + 1} returned ${files.length} files',
        );
        if (files.isEmpty && attempt < 2) {
          await Future.delayed(const Duration(milliseconds: 700));
        }
      }

      if (files.isEmpty) {
        _wals = [];
        return;
      }

      BleAudioCodec codec = await connection.getAudioCodec();
      var pd = await _device!.getDeviceInfo(connection);
      String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";

      List<Wal> wals = [];
      for (final file in files) {
        if (file.sizeBytes <= 0) continue;

        int fps = codec.getFramesPerSecond();
        int frameLen = codec.getFramesLengthInBytes();
        int seconds = fps > 0 && frameLen > 0 ? (file.sizeBytes / frameLen) ~/ fps : 0;
        if (seconds < 10) continue; // Skip very small files (<10s), same as PR #5905

        wals.add(
          Wal(
            codec: codec,
            timerStart: file.timestamp,
            status: WalStatus.miss,
            storage: WalStorage.sdcard,
            seconds: seconds,
            storageOffset: 0,
            storageTotalBytes: file.sizeBytes,
            fileNum: file.index,
            device: _device!.id,
            deviceModel: deviceModel,
            totalFrames: seconds * fps,
            syncedFrameOffset: 0,
          ),
        );
      }

      // Deterministic sync order: oldest -> newest (per PR #5905)
      wals.sort((a, b) => a.timerStart.compareTo(b.timerStart));

      _wals = wals;
      Logger.debug('StorageSync.refreshWalsFromDevice: Found ${wals.length} files to sync');
    } catch (e) {
      Logger.debug('StorageSync: Error refreshing wals from device: $e');
    }
  }

  @override
  Future deleteWal(Wal wal) async {
    if (wal.storage != WalStorage.sdcard || !_wals.any((w) => w.id == wal.id)) return;
    if (wal.device == _device?.id) await _deleteWalsOnDevice([wal]);
    _wals = _wals.where((w) => w.id != wal.id).toList();
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    final toDelete = _wals.where((w) => w.status == WalStatus.synced).toList();
    await _deleteWalsOnDevice(toDelete);
    _wals = _wals.where((w) => w.status != WalStatus.synced).toList();
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllPendingWals() async {
    final toDelete = _wals.where((w) => w.status == WalStatus.miss).toList();
    await _deleteWalsOnDevice(toDelete);
    _wals = _wals.where((w) => w.status != WalStatus.miss).toList();
    listener.onWalUpdated();
  }

  /// Deletes files on the device via CMD_DELETE_FILE. Firmware re-indexes files
  /// after each delete (higher indices shift down by 1), so delete highest index
  /// first to keep remaining fileNums valid.
  Future<void> _deleteWalsOnDevice(List<Wal> wals) async {
    if (wals.isEmpty || _device == null) return;
    final connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) {
      Logger.debug('StorageSync._deleteWalsOnDevice: no connection, skipping firmware delete');
      return;
    }
    final targets = wals.where((w) => w.fileNum >= 0).toList()..sort((a, b) => b.fileNum.compareTo(a.fileNum));
    final deletedIds = targets.map((w) => w.id).toSet();
    for (final wal in targets) {
      try {
        final ok = await connection.deleteStorageFile(wal.fileNum);
        Logger.debug('StorageSync._deleteWalsOnDevice: deleted fileNum=${wal.fileNum} ok=$ok');
        if (ok) {
          // Firmware shifts remaining indices down by 1 for any file above the deleted one.
          for (final other in _wals) {
            if (deletedIds.contains(other.id)) continue;
            if (other.fileNum > wal.fileNum) {
              other.fileNum -= 1;
            }
          }
        }
      } catch (e) {
        Logger.debug('StorageSync._deleteWalsOnDevice: failed fileNum=${wal.fileNum}: $e');
      }
    }
  }

  @override
  void start() {}

  @override
  Future stop() async {
    cancelSync();
    await _storageStream?.cancel();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    if (_device == null) {
      Logger.debug('StorageSync.syncAll: _device is null, returning');
      return null;
    }

    // Use already-populated _wals from getMissingWals() called earlier by WalSyncs.
    // Do NOT call getMissingWals() here — it creates a BLE subscription on the same
    // characteristic used for data transfer, causing subscription conflicts.
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    wals.sort((a, b) => a.timerStart.compareTo(b.timerStart));

    Logger.debug('StorageSync.syncAll: ${wals.length} files to sync');

    if (wals.isEmpty) {
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    DebugLogManager.logInfo('StorageSync: Starting sync of ${wals.length} files');

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    try {
      for (int i = 0; i < wals.length; i++) {
        if (_isCancelled) break;

        final wal = wals[i];
        Logger.debug(
          'StorageSync: Downloading file ${i + 1}/${wals.length} (index=${wal.fileNum}, size=${wal.storageTotalBytes})',
        );
        bool complete = await _syncSingleFile(wal, progress: progress, fileIndex: i, totalFiles: wals.length);

        // If transfer was interrupted (BLE disconnect), save what we have and stop
        if (!complete) {
          Logger.debug('StorageSync: File ${wal.fileNum} incomplete, stopping download phase');
          listener.onWalUpdated();
          break;
        }

        wal.status = WalStatus.synced;
        wal.deviceDownloadFraction = null;

        await _deleteTransferredFile(wal, wals);

        // The recording is on the phone now, so it leaves the device list. After
        // a delete the firmware re-indexes its files, so wal.fileNum then names
        // another recording, which deleteAllSyncedWals would delete. A delete
        // that timed out here can still finish on the device, so drop it either
        // way; a file the device kept is listed again by the next refresh.
        _wals = _wals.where((w) => !identical(w, wal)).toList();
        listener.onWalUpdated();
      }
    } catch (e) {
      Logger.debug('StorageSync: Error during sync: $e');
      DebugLogManager.logError(e, null, 'StorageSync failed', {'device': _device?.id});
    } finally {
      _isSyncing = false;
    }

    progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    return resp;
  }

  /// Delete the file from device after successful BLE transfer (per PR #5905),
  /// only on the connection that served it, then shift [remaining] down.
  /// Returns whether the device deleted the file.
  Future<bool> _deleteTransferredFile(Wal wal, List<Wal> remaining) async {
    if (wal.fileNum < 0) return false;
    try {
      final srcConn = _activeSyncConnection;
      final srcDeviceId = _activeSyncDeviceId;
      var sameSource = srcConn != null && srcDeviceId != null && _device?.id == srcDeviceId && !_isCancelled;
      if (sameSource && _activeSyncEpoch != null) {
        try {
          sameSource = srcConn.connectionEpoch == _activeSyncEpoch;
        } catch (_) {}
      }
      if (!sameSource) {
        Logger.debug(
          'StorageSync: device/connection changed during persistence — keeping fileNum ${wal.fileNum} on device',
        );
      } else if (srcConn != null) {
        Logger.debug("StorageSync: Deleting file index ${wal.fileNum} after successful BLE sync");
        bool deleted = await srcConn.deleteStorageFile(wal.fileNum);
        Logger.debug("StorageSync: Delete file ${wal.fileNum} result: $deleted");

        // After deletion, firmware shifts indices — decrement remaining WALs (per PR #5905)
        if (deleted) {
          for (final other in remaining) {
            if (identical(other, wal)) continue;
            if (other.fileNum > wal.fileNum) {
              other.fileNum = other.fileNum - 1;
            }
          }
        }
        return deleted;
      }
    } catch (e) {
      Logger.debug("StorageSync: Failed to delete file ${wal.fileNum}: $e (data is safe on phone)");
    }
    return false;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    // Resetting the sync state here would hijack a drain that is still reading.
    if (_isSyncing) throw Exception('Device transfer already in progress');

    _resetSyncState();
    _isSyncing = true;
    wal.isSyncing = true;
    wal.syncStartedAt = DateTime.now();
    listener.onWalUpdated();

    try {
      progress?.onWalSyncedProgress(0.0);
      final complete = await _syncSingleFile(wal, progress: progress);
      if (!complete) {
        // Same as an interrupted syncAll: keep the file on the device and the
        // recording pending, but tell the caller nothing was transferred.
        throw Exception('Device transfer incomplete; recording kept on device');
      }
      wal.status = WalStatus.synced;
      if (await _deleteTransferredFile(wal, _wals)) {
        // Its index now belongs to the next file, so it must not stay listed
        // for deleteAllSyncedWals to delete again.
        _wals = _wals.where((w) => !identical(w, wal)).toList();
      }
      progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    } catch (e) {
      Logger.debug('StorageSync: Error syncing file: $e');
      rethrow;
    } finally {
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.deviceDownloadFraction = null;
      _isSyncing = false;
      listener.onWalUpdated();
    }

    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  /// Download a single file from device storage to phone local disk,
  /// then register it with LocalWalSync for cloud upload.
  ///
  /// Follows PR #5905's proven BLE transfer pattern:
  /// - Data: [ts:4 BE][packed_opus:up to 440] per notification
  /// - Packed opus: [size:1][frame:size]... within each notification
  /// - Completion: single-byte [100] = end, [4] = empty, [0] = ack
  /// - Also completes when offset >= storageTotalBytes
  /// Returns true if transfer completed fully, false if interrupted (BLE disconnect, timeout).
  Future<bool> _syncSingleFile(
    Wal wal, {
    IWalSyncProgressListener? progress,
    int fileIndex = 0,
    int totalFiles = 1,
  }) async {
    final admittedGeneration = _localSync?.sessionGeneration ?? -1;
    Logger.debug(
      'StorageSync._syncSingleFile: fileNum=${wal.fileNum} size=${wal.storageTotalBytes} offset=${wal.storageOffset}',
    );
    if (_device == null) return false;

    var connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) throw Exception('Device not connected');

    _activeSyncDeviceId = _device!.id;
    _activeSyncConnection = connection;
    try {
      _activeSyncEpoch = connection.connectionEpoch;
    } catch (_) {
      _activeSyncEpoch = null;
    }
    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    final completer = Completer<bool>();
    _activeTransfer = completer;
    List<List<int>> bytesData = [];
    int offset = wal.storageOffset;
    bool firstDataReceived = false;
    bool hasError = false;
    bool hasParseGap = false;
    Timer? timeoutTimer;
    int packetCount = 0;

    // Throttle progress updates to every 200ms (per PR #5905)
    DateTime lastProgressUpdate = DateTime.now();
    const Duration progressInterval = Duration(milliseconds: 200);

    await _storageStream?.cancel();

    _storageStream = await connection.getBleStorageBytesListener(
      onStorageBytesReceived: (List<int> value) {
        if (_isCancelled) {
          unawaited(_requestFirmwareStopSync());
          if (!completer.isCompleted) {
            completer.completeError(Exception('Sync cancelled by user'));
          }
          return;
        }
        if (value.isEmpty || hasError || completer.isCompleted) return;

        packetCount++;

        if (!firstDataReceived) {
          firstDataReceived = true;
          timeoutTimer?.cancel();
          Logger.debug('StorageSync: First data received for file ${wal.fileNum} (${value.length} bytes)');
        }

        // Single byte = status/end signal (matching existing sdcard_wal_sync pattern)
        if (value.length == 1) {
          Logger.debug(
            'StorageSync: Status byte: ${value[0]} for file ${wal.fileNum} offset=$offset frames=${bytesData.length}',
          );
          if (value[0] == 0) {
            Logger.debug('StorageSync: Ack received (good to go)');
          } else if (value[0] == 3) {
            Logger.debug('StorageSync: Bad file size / cancel from device');
            hasError = true;
            if (!completer.isCompleted) {
              completer.complete(false);
            }
          } else if (value[0] == 4) {
            Logger.debug('StorageSync: File is empty');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else if (value[0] == 100) {
            Logger.debug('StorageSync: Transfer end signal');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else {
            Logger.debug('StorageSync: Error/status byte: ${value[0]}');
            hasError = true;
            if (!completer.isCompleted) {
              completer.complete(false);
            }
          }
          return;
        }

        int packetAudioBytes = 0;

        // Data packet: [timestamp:4 BE][audio_data:440] per notification.
        // Firmware writes 440-byte blocks with packed [size:1][frame:size]... and zero padding.
        // Each BLE notification is one complete block — parse independently.
        if (value.length <= 4) {
          hasParseGap = true;
        }
        if (value.length > 4) {
          var audioData = value.sublist(4);
          var audioLen = audioData.length;

          var packageOffset = 0;
          while (packageOffset < audioLen - 1) {
            var packageSize = audioData[packageOffset];
            if (packageSize == 0) {
              packageOffset += 1;
              continue;
            }
            if (packageOffset + 1 + packageSize >= audioLen) {
              break;
            }
            var frame = audioData.sublist(packageOffset + 1, packageOffset + 1 + packageSize);
            bytesData.add(frame);
            packageOffset += packageSize + 1;
          }
          packetAudioBytes = audioLen;
          offset += audioLen;
        }

        // Update speed and fire throttled progress
        if (packetAudioBytes > 0) {
          _updateSpeed(packetAudioBytes);

          final now = DateTime.now();
          if (now.difference(lastProgressUpdate) >= progressInterval) {
            lastProgressUpdate = now;
            if (wal.storageTotalBytes > 0) {
              double fileProgress = (offset / wal.storageTotalBytes).clamp(0.0, 1.0);
              double overallProgress = (fileIndex + fileProgress) / totalFiles;
              wal.deviceDownloadFraction = fileProgress;
              progress?.onWalSyncedProgress(
                overallProgress.clamp(0.0, 1.0),
                speedKBps: _currentSpeedKBps,
                phase: SyncPhase.downloadingFromDevice,
                currentFile: fileIndex + 1,
                totalFiles: totalFiles,
              );
            }
          }
        }

        // Check if we've received all expected data (per PR #5905)
        if (offset >= wal.storageTotalBytes) {
          Logger.debug(
            'StorageSync: File transfer complete: offset=$offset >= totalBytes=${wal.storageTotalBytes}, frames=${bytesData.length} pkts=$packetCount',
          );
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        }
      },
    );

    if (_storageStream == null) {
      throw Exception('Failed to set up storage listener');
    }

    // Complete immediately on BLE disconnect (stream closes)
    _storageStream!.onDone(() {
      if (!completer.isCompleted) {
        Logger.debug(
          'StorageSync: BLE stream closed for file ${wal.fileNum} (offset=$offset/${wal.storageTotalBytes}, frames=${bytesData.length})',
        );
        completer.complete(true);
      }
    });

    timeoutTimer = Timer(const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        hasError = true;
        Logger.debug('StorageSync: No data received for file ${wal.fileNum} within 5s');
        completer.completeError(TimeoutException('No data from device'));
      }
    });

    // Send CMD_READ_FILE: writeToStorage(fileIndex, command=0x11, offset=0)
    await connection.writeToStorage(wal.fileNum, 0x11, offset);

    Logger.debug(
      'StorageSync: Waiting for file ${wal.fileNum} transfer (expecting ${wal.storageTotalBytes} bytes from offset $offset)...',
    );

    bool endReached = false;
    try {
      endReached = await completer.future.timeout(const Duration(minutes: 10));
    } on TimeoutException {
      Logger.debug(
        'StorageSync: File ${wal.fileNum} OVERALL TIMEOUT. offset=$offset/${wal.storageTotalBytes} frames=${bytesData.length}',
      );
    } catch (e) {
      Logger.debug('StorageSync: File ${wal.fileNum} ERROR: $e. offset=$offset/${wal.storageTotalBytes}');
    } finally {
      if (_isCancelled || !endReached) {
        try {
          await connection.stopStorageSync();
          Logger.debug('StorageSync: STOP sent on the source connection');
        } catch (e) {
          Logger.debug('StorageSync: STOP failed: $e');
        }
      }
      await _storageStream?.cancel();
      _storageStream = null;
      if (identical(_activeTransfer, completer)) _activeTransfer = null;
      timeoutTimer.cancel();
      if (!endReached || hasError) wal.deviceDownloadFraction = null;
    }

    bool transferComplete = endReached &&
        offset >= wal.storageTotalBytes &&
        !hasError &&
        !hasParseGap &&
        !_isCancelled &&
        bytesData.isNotEmpty;

    if (bytesData.isEmpty) {
      Logger.debug('StorageSync: No opus frames parsed for file ${wal.fileNum} ($offset raw bytes)');
      return false;
    }

    var chunkSize = sdcardChunkSizeSecs * wal.codec.getFramesPerSecond();
    int totalFrames = bytesData.length;
    int accurateDuration = totalFrames ~/ wal.codec.getFramesPerSecond();
    int timerStart =
        wal.timerStart > 0 ? wal.timerStart : DateTime.now().millisecondsSinceEpoch ~/ 1000 - accurateDuration;
    // A file without a device timestamp gets an estimated start: one run per file.
    final clockRun = wal.timerStart > 0 ? null : (wal.clockRun ?? Wal.newClockRun());
    int bytesLeft = 0;

    try {
      while (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        await _writeChunkDurably(wal, chunk, timerStart, admittedGeneration, clockRun: clockRun);
        timerStart += chunk.length ~/ wal.codec.getFramesPerSecond();
      }

      if (bytesLeft < bytesData.length) {
        var chunk = bytesData.sublist(bytesLeft);
        await _writeChunkDurably(wal, chunk, timerStart, admittedGeneration, clockRun: clockRun);
      }
    } catch (e) {
      Logger.debug('StorageSync: durable write failed for file ${wal.fileNum}: $e');
      transferComplete = false;
    }

    Logger.debug(
      'StorageSync: File ${wal.fileNum} synced ($offset bytes, ${bytesData.length} frames, complete=$transferComplete)',
    );
    return transferComplete;
  }

  int _storageFileSeq = 0;

  Future<void> _writeChunkDurably(Wal wal, List<List<int>> chunk, int timerStart, int admittedGeneration,
      {String? clockRun}) async {
    final localSync = _localSync;
    if (localSync == null) throw StateError('LocalWalSync unavailable; chunk cannot be proven durable');
    await localSync.persistDeviceChunk(
        source: wal,
        frames: chunk,
        timerStart: timerStart,
        admittedGeneration: admittedGeneration,
        clockRun: clockRun,
        nextCollisionSequence: () => _storageFileSeq++);
  }
}
