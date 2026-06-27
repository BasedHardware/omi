import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:version/version.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class SDCardWalSyncImpl implements SDCardWalSync {
  List<Wal> _wals = const [];
  BtDevice? _device;

  StreamSubscription? _storageStream;

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

  static final Version _timestampMarkerMinVersion = Version.parse("3.0.16");

  SDCardWalSyncImpl(this.listener);

  bool _supportsTimestampMarkers() {
    if (_device == null) return false;
    try {
      return Version.parse(_device!.firmwareRevision) >= _timestampMarkerMinVersion;
    } catch (e) {
      return false;
    }
  }

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void cancelSync() {
    if (_isSyncing) {
      _isCancelled = true;
      Logger.debug("SDCardWalSync: Cancel requested");
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
    _totalBytesDownloaded = 0;
    _downloadStartTime = null;
    _currentSpeedKBps = 0.0;
  }

  void _updateSpeed(int bytesDownloaded) {
    _totalBytesDownloaded += bytesDownloaded;
    if (_downloadStartTime != null) {
      final elapsedSeconds = DateTime.now().difference(_downloadStartTime!).inMilliseconds / 1000.0;
      if (elapsedSeconds > 0) {
        _currentSpeedKBps = (_totalBytesDownloaded / 1024) / elapsedSeconds;
      }
    }
  }

  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  @override
  Future deleteWal(Wal wal) async {
    _wals.removeWhere((w) => w.id == wal.id);

    if (_device != null) {
      await _writeToStorage(_device!.id, wal.fileNum, 1, 0);
    }

    listener.onWalUpdated();
  }

  Future<List<Wal>> _getMissingWals() async {
    if (_device == null) {
      return [];
    }
    String deviceId = _device!.id;
    List<Wal> wals = [];
    var storageFiles = await _getStorageList(deviceId);
    if (storageFiles.isEmpty) {
      return [];
    }
    var totalBytes = storageFiles[0];
    if (totalBytes <= 0) {
      return [];
    }
    var storageOffset = storageFiles.length < 2 ? 0 : storageFiles[1];
    if (storageOffset > totalBytes) {
      Logger.debug("SDCard bad state, offset > total");
      storageOffset = 0;
    }

    BleAudioCodec codec = await _getAudioCodec(deviceId);
    if (totalBytes - storageOffset > 10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
      var seconds = ((totalBytes - storageOffset) / codec.getFramesLengthInBytes()) ~/ codec.getFramesPerSecond();
      // Use device-provided recording start timestamp if available (firmware >= 3.0.16), otherwise estimate
      int timerStart;
      if (_supportsTimestampMarkers() && storageFiles.length >= 3 && storageFiles[2] > 0) {
        timerStart = storageFiles[2];
      } else {
        timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - seconds;
      }
      Logger.debug(
        'SDCardWalSync: totalBytes=$totalBytes storageOffset=$storageOffset frameLengthInBytes=${codec.getFramesLengthInBytes()} fps=${codec.getFramesPerSecond()} calculatedSeconds=$seconds timerStart=$timerStart now=${DateTime.now().millisecondsSinceEpoch ~/ 1000}',
      );

      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        Logger.debug("SDCard: Failed to establish connection for device info");
        return wals;
      }
      var pd = await _device!.getDeviceInfo(connection);
      String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";

      wals.add(
        Wal(
          codec: codec,
          timerStart: timerStart,
          status: WalStatus.miss,
          storage: WalStorage.sdcard,
          seconds: seconds,
          storageOffset: storageOffset,
          storageTotalBytes: totalBytes,
          fileNum: 1,
          device: _device!.id,
          deviceModel: deviceModel,
          totalFrames: seconds * codec.getFramesPerSecond(),
          syncedFrameOffset: 0,
        ),
      );
    }

    return wals;
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
  }

  @override
  Future start() async {
    final syncingWal = _wals.where((w) => w.isSyncing).firstOrNull;
    _wals = await _getMissingWals();
    // Re-add the syncing WAL if it was lost
    if (syncingWal != null && !_wals.any((w) => w.id == syncingWal.id)) {
      _wals = [syncingWal, ..._wals];
    }
    listener.onWalUpdated();
  }

  @override
  Future stop() async {
    _wals = [];
    _storageStream?.cancel();
  }

  Future<bool> _writeToStorage(String deviceId, int numFile, int command, int offset) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(false);
    }
    return connection.writeToStorage(numFile, command, offset);
  }

  Future<StreamSubscription?> _getBleStorageBytesListener(
    String deviceId, {
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleStorageBytesListener(onStorageBytesReceived: onStorageBytesReceived);
  }

  Future<File> _flushToDisk(Wal wal, List<List<int>> chunk, int timerStart) async {
    final directory = await getApplicationDocumentsDirectory();
    String filePath = '${directory.path}/${wal.getFileNameByTimeStarts(timerStart)}';
    List<int> data = [];

    // Debug: Log first frame info
    if (chunk.isNotEmpty) {
      final firstFrame = chunk[0];
      final frameHex = firstFrame.take(8).map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ');
      Logger.debug(
        "SDCardWalSync _flushToDisk: ${chunk.length} frames, first frame size=${firstFrame.length}, hex: $frameHex",
      );
    }

    for (int i = 0; i < chunk.length; i++) {
      var frame = chunk[i];

      final byteFrame = ByteData(frame.length);
      for (int i = 0; i < frame.length; i++) {
        byteFrame.setUint8(i, frame[i]);
      }
      data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());
    }
    final file = File(filePath);
    await file.writeAsBytes(data);

    Logger.debug("SDCardWalSync _flushToDisk: Wrote ${data.length} bytes to $filePath");

    return file;
  }

  Future _readStorageBytesToFile(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback,
  ) async {
    if (_supportsTimestampMarkers()) {
      return _readStorageBytesToFileWithMarkers(wal, callback);
    }
    return _readStorageBytesToFileLegacy(wal, callback);
  }

  Future _readStorageBytesToFileLegacy(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback,
  ) async {
    var deviceId = wal.device;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;

    Logger.debug("_readStorageBytesToFileLegacy ${offset}");

    List<List<int>> bytesData = [];
    var chunkSize = sdcardChunkSizeSecs * 100;
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    bool hasError = false;
    bool firstDataReceived = false;
    Timer? timeoutTimer;

    _storageStream = await _getBleStorageBytesListener(
      deviceId,
      onStorageBytesReceived: (List<int> value) async {
        if (value.isEmpty || hasError) return;

        if (!firstDataReceived) {
          firstDataReceived = true;
          timeoutTimer?.cancel();
          Logger.debug('First data received, timeout cancelled');
        }

        if (value.length == 1) {
          Logger.debug('returned $value');
          if (value[0] == 0) {
            Logger.debug('good to go');
          } else if (value[0] == 3) {
            Logger.debug('bad file size. finishing...');
          } else if (value[0] == 4) {
            Logger.debug('file size is zero. going to next one....');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else if (value[0] == 100) {
            Logger.debug('end');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else {
            Logger.debug('Error bit returned');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          }
          return;
        }

        if (value.length == 83) {
          var amount = value[3];
          bytesData.add(value.sublist(4, 4 + amount));
          offset += 80;
        } else if (value.length == 440) {
          var packageOffset = 0;
          while (packageOffset < value.length - 1) {
            var packageSize = value[packageOffset];
            if (packageSize == 0) {
              packageOffset += packageSize + 1;
              continue;
            }
            if (packageOffset + 1 + packageSize >= value.length) {
              break;
            }
            var frame = value.sublist(packageOffset + 1, packageOffset + 1 + packageSize);
            bytesData.add(frame);
            packageOffset += packageSize + 1;
          }
          offset += value.length;
        }
      },
    );

    await _writeToStorage(deviceId, fileNum, 0, offset);

    timeoutTimer = Timer(const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        hasError = true;
        final error = TimeoutException('No data received from SD card within 5 seconds');
        Logger.debug('SD card read timeout: ${error.message}');
        DebugLogManager.logWarning('SD card BLE read timeout: no data in 5s', {'offset': offset});
        completer.completeError(error);
      }
    });

    try {
      await completer.future;
    } catch (e) {
      rethrow;
    } finally {
      await _storageStream?.cancel();
      timeoutTimer.cancel();
    }

    // After download: compute accurate duration from actual frame count
    if (!hasError && bytesData.isNotEmpty) {
      int totalFrames = bytesData.length;
      int accurateDuration = totalFrames ~/ wal.codec.getFramesPerSecond();
      int timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - accurateDuration;

      int bytesLeft = 0;
      int chunkOffset = wal.storageOffset;
      while (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        chunkOffset += chunkSize * wal.codec.getFramesLengthInBytes();
        try {
          var file = await _flushToDisk(wal, chunk, timerStart);
          await callback(file, chunkOffset, timerStart, chunk.length);
        } catch (e) {
          Logger.debug('Error in callback during chunking: $e');
          hasError = true;
          break;
        }
        timerStart += chunk.length ~/ wal.codec.getFramesPerSecond();
      }
      if (!hasError && bytesLeft < bytesData.length) {
        var chunk = bytesData.sublist(bytesLeft);
        chunkOffset += chunk.length * wal.codec.getFramesLengthInBytes();
        var file = await _flushToDisk(wal, chunk, timerStart);
        await callback(file, chunkOffset, timerStart, chunk.length);
      }
    }

    return;
  }

  Future _readStorageBytesToFileWithMarkers(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback,
  ) async {
    var deviceId = wal.device;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;
    int timerStart = wal.timerStart;

    Logger.debug("_readStorageBytesToFileWithMarkers ${offset}");

    List<List<int>> bytesData = [];
    var bytesLeft = 0;
    var chunkSize = sdcardChunkSizeSecs * wal.codec.getFramesPerSecond();
    List<MapEntry<int, int>> timestampMarkers = [];
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    bool hasError = false;
    bool firstDataReceived = false;
    Timer? timeoutTimer;

    _storageStream = await _getBleStorageBytesListener(
      deviceId,
      onStorageBytesReceived: (List<int> value) async {
        if (value.isEmpty || hasError) return;

        if (!firstDataReceived) {
          firstDataReceived = true;
          timeoutTimer?.cancel();
          Logger.debug('First data received, timeout cancelled');
        }

        if (value.length == 1) {
          Logger.debug('returned $value');
          if (value[0] == 0) {
            Logger.debug('good to go');
          } else if (value[0] == 3) {
            Logger.debug('bad file size. finishing...');
          } else if (value[0] == 4) {
            Logger.debug('file size is zero. going to next one....');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else if (value[0] == 100) {
            Logger.debug('end');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else {
            Logger.debug('Error bit returned');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          }
          return;
        }

        if (value.length == 83) {
          var amount = value[3];
          bytesData.add(value.sublist(4, 4 + amount));
          offset += 80;
        } else if (value.length == 440) {
          var packageOffset = 0;
          while (packageOffset < value.length - 1) {
            var packageSize = value[packageOffset];
            if (packageSize == 0) {
              packageOffset += 1;
              continue;
            }
            // Timestamp marker: 0xFF followed by 4-byte little-endian epoch
            if (packageSize == 0xFF && packageOffset + 5 <= value.length) {
              var epoch = value[packageOffset + 1] |
                  (value[packageOffset + 2] << 8) |
                  (value[packageOffset + 3] << 16) |
                  (value[packageOffset + 4] << 24);
              packageOffset += 5;
              if (epoch > 0) {
                timestampMarkers.add(MapEntry(bytesData.length, epoch));
                Logger.debug('Timestamp marker: epoch=$epoch at frame ${bytesData.length}');
              }
              continue;
            }
            if (packageOffset + 1 + packageSize >= value.length) {
              break;
            }
            var frame = value.sublist(packageOffset + 1, packageOffset + 1 + packageSize);
            bytesData.add(frame);
            packageOffset += packageSize + 1;
          }
          offset += value.length;
        }

        // Find the next marker boundary (if any) after bytesLeft
        int nextMarkerIdx = bytesData.length;
        for (var m in timestampMarkers) {
          if (m.key > bytesLeft) {
            nextMarkerIdx = m.key;
            break;
          }
        }

        // Chunk up to the next marker boundary or chunkSize, whichever comes first
        while (bytesData.length - bytesLeft >= chunkSize && bytesLeft + chunkSize <= nextMarkerIdx) {
          var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
          var chunkFrames = chunk.length;
          var chunkSecs = chunkFrames ~/ wal.codec.getFramesPerSecond();
          bytesLeft += chunkSize;
          try {
            var file = await _flushToDisk(wal, chunk, timerStart);
            await callback(file, offset, timerStart, chunkFrames);
          } catch (e) {
            Logger.debug('Error in callback during chunking: $e');
            hasError = true;
            if (!completer.isCompleted) {
              completer.completeError(e);
            }
          }
          timerStart += chunkSecs;
        }

        // If we've reached a marker boundary, flush remaining frames before it and advance timerStart
        if (timestampMarkers.any((m) => m.key == nextMarkerIdx) &&
            nextMarkerIdx <= bytesData.length &&
            bytesLeft < nextMarkerIdx) {
          var chunk = bytesData.sublist(bytesLeft, nextMarkerIdx);
          var chunkFrames = chunk.length;
          if (chunkFrames > 0) {
            var chunkSecs = chunkFrames ~/ wal.codec.getFramesPerSecond();
            bytesLeft = nextMarkerIdx;
            try {
              var file = await _flushToDisk(wal, chunk, timerStart);
              await callback(file, offset, timerStart, chunkFrames);
            } catch (e) {
              Logger.debug('Error flushing segment at marker: $e');
              hasError = true;
              if (!completer.isCompleted) completer.completeError(e);
            }
            timerStart += chunkSecs;
          } else {
            bytesLeft = nextMarkerIdx;
          }
          // Apply the marker's epoch
          for (var m in timestampMarkers) {
            if (m.key == nextMarkerIdx) {
              timerStart = m.value;
              break;
            }
          }
        }
      },
    );

    await _writeToStorage(deviceId, fileNum, 0, offset);

    timeoutTimer = Timer(const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        hasError = true;
        final error = TimeoutException('No data received from SD card within 5 seconds');
        Logger.debug('SD card read timeout: ${error.message}');
        DebugLogManager.logWarning('SD card BLE read timeout: no data in 5s', {'offset': offset});
        completer.completeError(error);
      }
    });

    try {
      await completer.future;
    } catch (e) {
      rethrow;
    } finally {
      await _storageStream?.cancel();
      timeoutTimer.cancel();
    }

    // Flush remaining data, respecting any unprocessed timestamp markers
    if (!hasError && bytesLeft < bytesData.length) {
      List<List<int>> segments = [];
      int segStart = bytesLeft;
      int segEpoch = timerStart;
      for (var marker in timestampMarkers) {
        if (marker.key > bytesLeft && marker.key < bytesData.length) {
          if (marker.key > segStart) {
            segments.add([segStart, marker.key, segEpoch]);
          }
          segStart = marker.key;
          segEpoch = marker.value;
        }
      }
      if (segStart < bytesData.length) {
        segments.add([segStart, bytesData.length, segEpoch]);
      }

      for (var seg in segments) {
        int sStart = seg[0];
        int sEnd = seg[1];
        int sEpoch = seg[2];
        var chunk = bytesData.sublist(sStart, sEnd);
        var chunkFrames = chunk.length;
        if (chunkFrames > 0) {
          var file = await _flushToDisk(wal, chunk, sEpoch);
          await callback(file, offset, sEpoch, chunkFrames);
        }
      }
    }

    return;
  }

  Future<SyncLocalFilesResponse> _syncWal(final Wal wal, Function(int offset, double speedKBps)? updates) async {
    Logger.debug("SDCard sync (two-phase): ${wal.id} byte offset: ${wal.storageOffset} ts ${wal.timerStart}");

    if (_localSync == null) {
      Logger.debug("SDCard: ERROR - LocalWalSync not available, aborting to preserve data safety");
      DebugLogManager.logError('SD card sync aborted: LocalWalSync not available', null, null);
      throw Exception('Local sync service not available. Cannot safely download SD card data.');
    }

    int chunksDownloaded = 0;
    int lastOffset = wal.storageOffset;
    int totalBytesToDownload = wal.storageTotalBytes - wal.storageOffset;

    Logger.debug(
      "SDCard Phase 1: Downloading ~${(totalBytesToDownload / 1024).toStringAsFixed(1)} KB to phone storage",
    );
    DebugLogManager.logEvent('sdcard_ble_download_started', {
      'walId': wal.id,
      'totalBytes': totalBytesToDownload,
      'codec': wal.codec.toString(),
    });

    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    try {
      await _readStorageBytesToFile(wal, (File file, int offset, int timerStart, int chunkFrames) async {
        if (_isCancelled) {
          throw Exception('Sync cancelled by user');
        }

        int bytesInChunk = offset - lastOffset;
        _updateSpeed(bytesInChunk);
        await _registerSingleChunk(wal, file, timerStart, chunkFrames);
        chunksDownloaded++;
        lastOffset = offset;

        listener.onWalUpdated();
        if (updates != null) {
          updates(offset, _currentSpeedKBps);
        }

        Logger.debug(
          "SDCard: Chunk $chunksDownloaded downloaded (ts: $timerStart, speed: ${_currentSpeedKBps.toStringAsFixed(1)} KB/s)",
        );
      });
    } catch (e) {
      await _storageStream?.cancel();
      Logger.debug('SDCard download failed: $e');
      DebugLogManager.logError(e, null, 'SD card BLE download failed: ${e.toString()}', {
        'chunksDownloaded': chunksDownloaded,
        'walId': wal.id,
      });
      if (chunksDownloaded > 0) {
        Logger.debug("SDCard: $chunksDownloaded chunks saved before failure");
      }
      rethrow;
    }

    if (chunksDownloaded == 0) {
      Logger.debug("SDCard: No chunks downloaded");
      DebugLogManager.logWarning('SD card BLE download: no chunks received', {'walId': wal.id});
      return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    }

    Logger.debug("SDCard Phase 1 complete: $chunksDownloaded chunks downloaded");
    DebugLogManager.logInfo('SD card BLE download complete', {'chunks': chunksDownloaded});

    Logger.debug("SDCard Phase 3: Clearing SD card storage");
    await _writeToStorage(wal.device, wal.fileNum, 1, 0);

    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  Future<void> _registerSingleChunk(Wal wal, File file, int timerStart, int chunkFrames) async {
    if (_localSync == null) {
      Logger.debug("SDCard: WARNING - Cannot register chunk, LocalWalSync not available");
      return;
    }

    int chunkSeconds = chunkFrames ~/ wal.codec.getFramesPerSecond();

    Wal localWal = Wal(
      codec: wal.codec,
      channel: wal.channel,
      sampleRate: wal.sampleRate,
      timerStart: timerStart,
      filePath: file.path.split('/').last,
      storage: WalStorage.disk,
      status: WalStatus.miss,
      device: wal.device,
      deviceModel: wal.deviceModel,
      seconds: chunkSeconds,
      totalFrames: chunkFrames,
      syncedFrameOffset: 0,
      originalStorage: WalStorage.sdcard,
    );

    await _localSync!.addExternalWal(localWal);
    Logger.debug(
      "SDCard: Registered chunk (ts: $timerStart) with LocalWalSync - codec=${localWal.codec}, sampleRate=${localWal.sampleRate}, channel=${localWal.channel}",
    );
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) {
      Logger.debug("SDCardWalSync: All synced!");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    for (var i = wals.length - 1; i >= 0; i--) {
      if (_isCancelled) {
        Logger.debug("SDCardWalSync: Sync cancelled before processing WAL ${wals[i].id}");
        break;
      }

      var wal = wals[i];

      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
      wal.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();

      final storageOffsetStarts = wal.storageOffset;
      final totalBytes = wal.storageTotalBytes - storageOffsetStarts;

      try {
        var partialRes = await _syncWal(wal, (offset, speedKBps) {
          wal.storageOffset = offset;
          wal.syncSpeedKBps = speedKBps;

          final bytesRemaining = wal.storageTotalBytes - offset;
          if (speedKBps > 0) {
            wal.syncEtaSeconds = (bytesRemaining / 1024 / speedKBps).round();
          }

          final bytesDownloaded = offset - storageOffsetStarts;
          final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;

          progress?.onWalSyncedProgress(progressPercent.clamp(0.0, 1.0), speedKBps: speedKBps);
          listener.onWalUpdated();
        });

        resp.newConversationIds.addAll(
          partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
        );
        resp.updatedConversationIds.addAll(
          partialRes.updatedConversationIds.where(
            (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
          ),
        );

        wal.status = WalStatus.synced;
      } catch (e) {
        Logger.debug("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
        DebugLogManager.logError(e, null, 'SD card syncAll WAL failed: ${e.toString()}', {'walId': wal.id});
        wal.isSyncing = false;
        wal.syncStartedAt = null;
        wal.syncEtaSeconds = null;
        wal.syncSpeedKBps = null;
        wal.syncMethod = SyncMethod.ble;
        listener.onWalUpdated();
        _resetSyncState();
        rethrow;
      }

      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      wal.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();
    }

    _resetSyncState();
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    var walToSync = _wals.where((w) => w == wal).firstOrNull;
    if (walToSync == null) {
      Logger.debug("SDCardWalSync: WAL not found in _wals, skipping sync");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    walToSync.syncMethod = SyncMethod.ble;
    listener.onWalUpdated();

    final storageOffsetStarts = wal.storageOffset;
    final totalBytes = wal.storageTotalBytes - storageOffsetStarts;

    try {
      var partialRes = await _syncWal(wal, (offset, speedKBps) {
        walToSync.storageOffset = offset;
        walToSync.syncSpeedKBps = speedKBps;

        final bytesRemaining = walToSync.storageTotalBytes - offset;
        if (speedKBps > 0) {
          walToSync.syncEtaSeconds = (bytesRemaining / 1024 / speedKBps).round();
        }

        final bytesDownloaded = offset - storageOffsetStarts;
        final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;

        progress?.onWalSyncedProgress(progressPercent.clamp(0.0, 1.0), speedKBps: speedKBps);
        listener.onWalUpdated();
      });

      resp.newConversationIds.addAll(
        partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
      );
      resp.updatedConversationIds.addAll(
        partialRes.updatedConversationIds.where(
          (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
        ),
      );

      wal.status = WalStatus.synced;
    } catch (e) {
      Logger.debug("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
      DebugLogManager.logError(e, null, 'SD card single WAL sync failed: ${e.toString()}', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      walToSync.syncSpeedKBps = null;
      walToSync.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();
      _resetSyncState();
      rethrow;
    }

    wal.isSyncing = false;
    wal.syncStartedAt = null;
    wal.syncEtaSeconds = null;
    wal.syncSpeedKBps = null;
    wal.syncMethod = SyncMethod.ble;

    listener.onWalUpdated();
    _resetSyncState();
    return resp;
  }

  @override
  void setDevice(BtDevice? device) async {
    _device = device;
    final syncingWal = _wals.where((w) => w.isSyncing).firstOrNull;
    _wals = await _getMissingWals();
    // Re-add the syncing WAL if it was lost
    if (syncingWal != null && !_wals.any((w) => w.id == syncingWal.id)) {
      _wals = [syncingWal, ..._wals];
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

  @override
  Future<void> deleteAllPendingWals() async {
    final pendingWals = _wals.where((w) => w.status == WalStatus.miss || w.status == WalStatus.corrupted).toList();
    for (final wal in pendingWals) {
      await deleteWal(wal);
    }
  }
}
