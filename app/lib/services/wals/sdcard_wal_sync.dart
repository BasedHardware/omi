import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:version/version.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/transports/tcp_transport.dart';
import 'package:omi/services/devices/wifi_sync_error.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wifi/wifi_network_service.dart';

class SDCardWalSyncImpl implements SDCardWalSync {
  List<Wal> _wals = const [];
  BtDevice? _device;

  StreamSubscription? _storageStream;

  IWalSyncListener listener;
  LocalWalSync? _localSync;

  bool _isCancelled = false;
  bool _isSyncing = false;
  String? _activeSyncDeviceId;
  bool _firmwareStopRequested = false;
  TcpTransport? _activeTcpTransport;
  Completer<void>? _activeTransferCompleter;
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
      Logger.debug("SDCardWalSync: Cancel requested, actively tearing down connections");

      final storageSub = _storageStream;
      if (storageSub != null) {
        unawaited(storageSub.cancel());
      }
      unawaited(_requestFirmwareStopSync());

      // Actively disconnect TCP transport to stop data flow immediately
      _activeTcpTransport?.disconnect();

      // Complete the transfer completer so the await unblocks immediately
      if (_activeTransferCompleter != null && !_activeTransferCompleter!.isCompleted) {
        _activeTransferCompleter!.complete();
      }
    }
  }

  Future<void> _requestFirmwareStopSync() async {
    if (_firmwareStopRequested) return;
    _firmwareStopRequested = true;

    final deviceId = _activeSyncDeviceId ?? _device?.id;
    if (deviceId == null || deviceId.isEmpty) {
      Logger.debug("SDCardWalSync: Stop sync requested but no active device id");
      return;
    }

    try {
      final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        Logger.debug("SDCardWalSync: Stop sync skipped - connection unavailable");
        return;
      }
      final stopped = await connection.stopStorageSync();
      Logger.debug("SDCardWalSync: STOP command sent to firmware (ok=$stopped)");
    } catch (e) {
      Logger.debug("SDCardWalSync: Failed to send STOP command: $e");
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
    _activeSyncDeviceId = null;
    _firmwareStopRequested = false;
    _totalBytesDownloaded = 0;
    _downloadStartTime = null;
    _currentSpeedKBps = 0.0;
    _wifiSpeedWindowStart = null;
    _wifiSpeedWindowBytes = 0;
    _lastProgressUpdate = null;
    _activeTcpTransport = null;
    _activeTransferCompleter = null;
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

  // WiFi speed calculation
  DateTime? _wifiSpeedWindowStart;
  int _wifiSpeedWindowBytes = 0;
  DateTime? _lastProgressUpdate;
  static const Duration _speedUpdateInterval = Duration(seconds: 1);
  static const Duration _progressUpdateInterval = Duration(milliseconds: 200);
  static const double _speedEmaAlpha = 0.25; // EMA smoothing factor (0=sticky,1=instant)

  /// Returns (shouldUpdateProgress, shouldUpdateSpeed)
  (bool, bool) _updateWifiSpeed(int bytesDownloaded) {
    _totalBytesDownloaded += bytesDownloaded;
    _wifiSpeedWindowBytes += bytesDownloaded;
    final now = DateTime.now();

    // Initialize timestamps
    _wifiSpeedWindowStart ??= now;
    _lastProgressUpdate ??= now;

    bool shouldUpdateSpeed = false;
    bool shouldUpdateProgress = false;

    final windowDuration = now.difference(_wifiSpeedWindowStart!);
    if (windowDuration >= _speedUpdateInterval) {
      final windowSeconds = windowDuration.inMilliseconds / 1000.0;
      if (windowSeconds > 0) {
        final instantSpeed = (_wifiSpeedWindowBytes / 1024) / windowSeconds;
        // EMA smoothing: blend instant speed with previous speed
        _currentSpeedKBps = _currentSpeedKBps > 0
            ? _speedEmaAlpha * instantSpeed + (1 - _speedEmaAlpha) * _currentSpeedKBps
            : instantSpeed;
      }
      _wifiSpeedWindowStart = now;
      _wifiSpeedWindowBytes = 0;
      shouldUpdateSpeed = true;
    }

    final progressDuration = now.difference(_lastProgressUpdate!);
    if (progressDuration >= _progressUpdateInterval) {
      _lastProgressUpdate = now;
      shouldUpdateProgress = true;
    }

    return (shouldUpdateProgress, shouldUpdateSpeed);
  }

  void _finalizeWifiSpeed() {
    if (_wifiSpeedWindowStart != null && _wifiSpeedWindowBytes > 0) {
      final windowSeconds = DateTime.now().difference(_wifiSpeedWindowStart!).inMilliseconds / 1000.0;
      if (windowSeconds > 0) {
        _currentSpeedKBps = (_wifiSpeedWindowBytes / 1024) / windowSeconds;
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
      var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection != null) {
        await connection.deleteFile(wal.fileNum);
      }
    }

    listener.onWalUpdated();
  }

  Future<List<Wal>> _getMissingWals() async {
    if (_device == null) {
      return [];
    }
    String deviceId = _device!.id;
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    var storageFiles = await _getStorageList(deviceId);
    if (storageFiles.isEmpty) {
      return [];
    }
    var totalBytes = storageFiles[0];
    if (totalBytes <= 0) {
      return [];
    }

    int fileCount = storageFiles.length >= 2 ? storageFiles[1] : 0;
    BleAudioCodec codec = await _getAudioCodec(deviceId);

    // New multi-file protocol only: CMD_LIST_FILES
    if (fileCount > 0) {
      // Stop any active auto-sync first to avoid notification conflicts
      await connection.stopStorageSync();
      await Future.delayed(const Duration(milliseconds: 500));

      List<StorageFile> files = [];
      for (int attempt = 0; attempt < 3 && files.isEmpty; attempt++) {
        files = await connection.listFiles();
        if (files.isEmpty && attempt < 2) {
          Logger.debug("SDCardWalSync: listFiles attempt ${attempt + 1} empty, retrying...");
          await Future.delayed(const Duration(milliseconds: 700));
        }
      }

      if (files.isNotEmpty) {
        return _buildWalsFromFileList(deviceId, codec, files);
      }

      Logger.debug("SDCardWalSync: listFiles failed while storage reports fileCount=$fileCount");
    }

    return [];
  }

  /// Build WAL list from file list response (new multi-file protocol)
  Future<List<Wal>> _buildWalsFromFileList(String deviceId, BleAudioCodec codec, List<StorageFile> files) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    var pd = await _device!.getDeviceInfo(connection);
    String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";

    List<Wal> wals = [];
    for (var file in files) {
      if (file.size <= 0) continue;

      var seconds = (file.size / codec.getFramesLengthInBytes()) ~/ codec.getFramesPerSecond();
      if (seconds < 10) continue; // Skip very small files (<10s)

      wals.add(Wal(
        codec: codec,
        timerStart: file.timestamp,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        seconds: seconds,
        storageOffset: 0,
        storageTotalBytes: file.size,
        fileNum: file.index,
        device: deviceId,
        deviceModel: deviceModel,
        totalFrames: seconds * codec.getFramesPerSecond(),
        syncedFrameOffset: 0,
      ));
    }

    // Deterministic sync order: oldest -> newest
    wals.sort((a, b) => a.timerStart.compareTo(b.timerStart));

    Logger.debug("SDCardWalSync: Built ${wals.length} WALs from ${files.length} files");
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
    Function(File f, int offset, int timerStart, int chunkFrames) callback, {
    void Function(int offset, int packetBytes)? onPacketReceived,
  }) async {
    if (_supportsTimestampMarkers()) {
      return _readStorageBytesToFileWithMarkers(wal, callback);
    }
    return _readStorageBytesToFileLegacy(wal, callback, onPacketReceived: onPacketReceived);
  }

  Future _readStorageBytesToFileLegacy(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback, {
    void Function(int offset, int packetBytes)? onPacketReceived,
  }) async {
    var deviceId = wal.device;
    _activeSyncDeviceId = deviceId;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;

    Logger.debug("_readStorageBytesToFileLegacy offset=$offset fileNum=$fileNum");

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
        if (_isCancelled) {
          await _requestFirmwareStopSync();
          if (!completer.isCompleted) {
            completer.completeError(Exception('Sync cancelled by user'));
          }
          return;
        }
        if (value.isEmpty || hasError) return;

        if (!firstDataReceived) {
          firstDataReceived = true;
          timeoutTimer?.cancel();
          Logger.debug('First data received, timeout cancelled');
        }

        // Single byte = status/end signal
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
            Logger.debug('Error/status byte: ${value[0]}');
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          }
          return;
        }

        int packetAudioBytes = 0;

        // New protocol: [timestamp:4 BE][audio_data:up to 440] (5-444 bytes)
        if (value.length > 4) {
          // Skip 4-byte timestamp prefix, extract audio data
          var audioData = value.sublist(4);
          var audioLen = audioData.length;

          // Parse packed opus frames from audio data: [size:1][frame:size]...
          var packageOffset = 0;
          while (packageOffset < audioLen - 1) {
            var packageSize = audioData[packageOffset];
            if (packageSize == 0) {
              packageOffset += 1;
              continue;
            }
            if (packageOffset + 1 + packageSize > audioLen) {
              break;
            }
            var frame = audioData.sublist(packageOffset + 1, packageOffset + 1 + packageSize);
            bytesData.add(frame);
            packageOffset += packageSize + 1;
          }
          packetAudioBytes = audioLen;
          offset += audioLen;
        }
        // Fire intermediate per-packet progress (throttled by caller)
        if (packetAudioBytes > 0) {
          onPacketReceived?.call(offset, packetAudioBytes);
        }

        // Check if we've received all expected data
        if (offset >= wal.storageTotalBytes) {
          Logger.debug('File transfer complete: offset=$offset >= totalBytes=${wal.storageTotalBytes}');
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        }
      },
    );

    // Send read command (new protocol only): CMD_READ_FILE (0x11)
    await _writeToStorage(deviceId, fileNum, 0x11, offset);

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
      if (_isCancelled) {
        await _requestFirmwareStopSync();
      }
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
              var epoch =
                  value[packageOffset + 1] |
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

    Logger.debug("SDCard Phase 1: Downloading ~${(totalBytesToDownload / 1024).toStringAsFixed(1)} KB (protocol=new)");
    DebugLogManager.logEvent('sdcard_ble_download_started', {
      'walId': wal.id,
      'totalBytes': totalBytesToDownload,
      'codec': wal.codec.toString(),
    });

    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    // Throttle intermediate progress updates to every 200 ms.
    DateTime _lastBleProgressUpdate = DateTime.now();
    const Duration _bleProgressInterval = Duration(milliseconds: 200);

    try {
      await _readStorageBytesToFile(
        wal,
        (File file, int offset, int timerStart, int chunkFrames) async {
          if (_isCancelled) {
            throw Exception('Sync cancelled by user');
          }

          // Speed already accumulated per-packet in onPacketReceived; no double-count here.
          await _registerSingleChunk(wal, file, timerStart, chunkFrames);
          chunksDownloaded++;
          lastOffset = offset;

          // Fire definitive progress at chunk boundary
          if (updates != null) updates(offset, _currentSpeedKBps);
          listener.onWalUpdated();

          Logger.debug(
              "SDCard: Chunk $chunksDownloaded downloaded (ts: $timerStart, speed: ${_currentSpeedKBps.toStringAsFixed(1)} KB/s)");
        },
        onPacketReceived: (int offset, int packetBytes) {
          // Per-packet intermediate progress (fired every ~440 bytes, throttled)
          _updateSpeed(packetBytes);
          final now = DateTime.now();
          if (now.difference(_lastBleProgressUpdate) >= _bleProgressInterval) {
            _lastBleProgressUpdate = now;
            if (updates != null) updates(offset, _currentSpeedKBps);
          }
        },
      );
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

    // Deletion is now handled by the caller (syncAll) after confirming receipt.
    // For BLE: caller deletes after each file.
    // For WiFi: caller deletes after all files are received.

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
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    // Always process oldest -> newest regardless source ordering.
    wals.sort((a, b) => a.timerStart.compareTo(b.timerStart));
    if (wals.isEmpty) {
      Logger.debug("SDCardWalSync: All synced!");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    // Iterate oldest -> newest
    for (var i = 0; i < wals.length; i++) {
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

        // BLE sync: delete file from firmware after successful download
        if (wal.fileNum >= 0) {
          try {
            var connection = await ServiceManager.instance().device.ensureConnection(wal.device);
            if (connection != null) {
              Logger.debug("SDCardWalSync: Deleting file index ${wal.fileNum} after successful BLE sync");
              bool deleted = await connection.deleteFile(wal.fileNum);
              Logger.debug("SDCardWalSync: Delete file ${wal.fileNum} result: $deleted");

              // After deletion, file indices shift for all files that had higher index.
              for (var j = 0; j < wals.length; j++) {
                if (j == i) continue;
                if (wals[j].fileNum > wal.fileNum) {
                  wals[j].fileNum = wals[j].fileNum - 1;
                }
              }
            }
          } catch (e) {
            Logger.debug("SDCardWalSync: Failed to delete file ${wal.fileNum}: $e (data is safe on phone)");
          }
        }
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
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    // Per-file sync is no longer supported. Redirect to syncAll which
    // syncs all files oldest→newest with proper delete-after-download.
    Logger.debug("SDCardWalSync: syncWal called - redirecting to syncAll (per-file sync disabled)");
    return syncAll(progress: progress, connectionListener: connectionListener);
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

  @override
  Future<bool> isWifiSyncSupported() async {
    if (_device == null) {
      Logger.debug("SDCardWalSync WiFi: No device connected");
      return false;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) {
      Logger.debug("SDCardWalSync WiFi: Could not get device connection");
      return false;
    }
    return await connection.isWifiSyncSupported();
  }

  // AP-mode compatibility stubs (credentials are not used in AP flow)
  @override
  Future<bool> setWifiCredentials(String ssid, String password) async {
    // In AP mode, credentials are not needed - SSID is auto-generated from device ID
    debugPrint("SDCardWalSync: setWifiCredentials called but not needed in AP mode");
    return true;
  }

  @override
  Future<void> clearWifiCredentials() async {
    // No-op in AP mode
  }

  @override
  Future<void> loadWifiCredentials() async {
    // No-op in AP mode
  }

  @override
  Map<String, String?>? getWifiCredentials() {
    // In AP mode, return null - credentials are auto-generated
    return null;
  }

  void _reconnectBleAfterCancel(String deviceId) {
    Future(() async {
      try {
        await Future.delayed(const Duration(seconds: 1));
        final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
        if (conn != null) {
          await conn.stopWifiSync();
          debugPrint("SDCardWalSync WiFi: Background BLE reconnect + stopWifiSync succeeded");
        }
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Background BLE reconnect failed (non-fatal): $e");
      }
    });
  }

  /// Helper to clean up WiFi sync resources
  Future<void> _cleanupWifiSync(
    TcpTransport? tcpTransport,
    WifiNetworkService? wifiNetwork,
    String? ssid,
    DeviceConnection? connection, {
    String? deviceId,
  }) async {
    ServiceManager.instance().device.setWifiSyncInProgress(false);

    try {
      await tcpTransport?.disconnect();
    } catch (e) {
      debugPrint("SDCardWalSync WiFi: Error disconnecting transport: $e");
    }

    if (ssid != null && wifiNetwork != null) {
      try {
        await wifiNetwork.disconnectFromAp(ssid);
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Error disconnecting from AP: $e");
      }
    }

    try {
      DeviceConnection? conn = connection;
      if (conn == null && deviceId != null) {
        conn = await ServiceManager.instance().device.ensureConnection(deviceId);
      }
      if (conn != null) {
        await conn.stopWifiSync();
      }
    } catch (e) {
      debugPrint("SDCardWalSync WiFi: Error stopping WiFi sync on device: $e");
    }

    _resetSyncState();
  }

  @override
  Future<SyncLocalFilesResponse?> syncWithWifi({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    wals.sort((a, b) => a.timerStart.compareTo(b.timerStart));
    if (wals.isEmpty) {
      Logger.debug("SDCardWalSync WiFi: All synced!");
      return null;
    }

    if (_device == null) {
      Logger.debug("SDCardWalSync WiFi: No device connected");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    final deviceId = _device!.id;

    // Set WAL sync state early so UI updates immediately
    final wal = wals.last;
    wal.isSyncing = true;
    wal.syncStartedAt = DateTime.now();
    wal.syncMethod = SyncMethod.wifi;
    listener.onWalUpdated();

    final totalBytes = wal.storageTotalBytes - wal.storageOffset;
    DebugLogManager.logEvent('sdcard_wifi_sync_started', {
      'walId': wal.id,
      'totalBytes': totalBytes,
      'deviceId': deviceId,
    });

    final ssid = WifiNetworkService.generateSsid(deviceId);
    final password = WifiNetworkService.generatePassword(deviceId);
    debugPrint("SDCardWalSync WiFi: Starting sync with device AP SSID: $ssid (deviceId: $deviceId)");

    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      Logger.debug("SDCardWalSync WiFi: Failed to get device connection");
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      listener.onWalUpdated();
      _resetSyncState();
      return null;
    }

    final wifiNetwork = WifiNetworkService();
    TcpTransport? tcpTransport;

    try {
      // Notify: Enabling device WiFi
      connectionListener?.onEnablingDeviceWifi();

      debugPrint("SDCardWalSync WiFi: Step 1 - Configuring device AP with SSID: $ssid");
      var setupResult = await connection.setupWifiSync(ssid, password);

      // If a previous session is still running, stop it and retry
      if (!setupResult.success && setupResult.errorCode == WifiSyncErrorCode.sessionAlreadyRunning) {
        debugPrint("SDCardWalSync WiFi: Previous session running, stopping it first...");
        await connection.stopWifiSync();
        await Future.delayed(const Duration(seconds: 1));
        setupResult = await connection.setupWifiSync(ssid, password);
      }

      if (!setupResult.success) {
        _resetSyncState();
        final errorMessage = setupResult.errorMessage ?? 'Failed to setup WiFi on device';
        final errorCode = setupResult.errorCode;
        DebugLogManager.logError('SD card WiFi setup failed: $errorMessage', null, null, {
          'errorCode': errorCode?.code.toRadixString(16) ?? 'none',
        });
        if (errorCode != null) {
          debugPrint(
            "SDCardWalSync WiFi: Setup failed with error code 0x${errorCode.code.toRadixString(16)}: ${errorCode.userMessage}",
          );
          connectionListener?.onConnectionFailed(errorCode.userMessage);
          throw WifiSyncException(errorMessage, errorCode: errorCode);
        } else {
          connectionListener?.onConnectionFailed(errorMessage);
          throw WifiSyncException(errorMessage);
        }
      }

      debugPrint("SDCardWalSync WiFi: Step 2 - Waiting 2 seconds before sending start command...");
      await Future.delayed(const Duration(seconds: 2));

      final startSuccess = await connection.startWifiSync();
      if (!startSuccess) {
        _resetSyncState();
        connectionListener?.onConnectionFailed('Failed to start device WiFi');
        throw WifiSyncException('Failed to start device WiFi AP');
      }

      // Notify: Connecting to device
      connectionListener?.onConnectingToDevice();

      // Wait for device to set up its WiFi AP before phone tries to connect
      debugPrint("SDCardWalSync WiFi: Step 3 - Waiting for device AP to become available...");
      await Future.delayed(const Duration(seconds: 8));

      debugPrint("SDCardWalSync WiFi: Step 4 - Connecting phone to device WiFi AP");
      final wifiResult = await wifiNetwork.connectToAp(ssid, password: password);
      if (!wifiResult.success) {
        await _cleanupWifiSync(null, wifiNetwork, ssid, connection, deviceId: deviceId);
        final errorMsg = wifiResult.errorMessage ?? wifiResult.error?.userMessage ?? 'Failed to connect to device WiFi';
        DebugLogManager.logError('SD card WiFi AP connection failed: $errorMsg', null, null);
        connectionListener?.onConnectionFailed(errorMsg);
        throw WifiSyncException('WiFi connection failed: $errorMsg');
      }

      // Step 6: Start TCP server and wait for device to connect
      const tcpPort = 12345;
      debugPrint("SDCardWalSync WiFi: Step 6 - Starting TCP server on port $tcpPort");
      tcpTransport = TcpTransport(deviceId, port: tcpPort, connectionTimeout: const Duration(seconds: 60));
      _activeTcpTransport = tcpTransport;
      try {
        await tcpTransport.connect();
        debugPrint("SDCardWalSync WiFi: Device connected to TCP server!");
        // Notify: Connected successfully
        connectionListener?.onConnected();
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: TCP server error: $e");
        DebugLogManager.logError(e, null, 'SD card WiFi TCP connection failed: ${e.toString()}');
        await _cleanupWifiSync(tcpTransport, wifiNetwork, ssid, connection, deviceId: deviceId);
        connectionListener?.onConnectionFailed('Device did not connect');
        throw WifiSyncException('Device did not connect to TCP server: $e');
      }

      // Setup WiFi status listener (optional, for debugging)
      StreamSubscription? wifiStatusSubscription;
      try {
        wifiStatusSubscription = await connection.getWifiSyncStatusListener(
          onStatusReceived: (status) {
            String statusName;
            switch (status) {
              case 0:
                statusName = 'OFF';
                break;
              case 1:
                statusName = 'SHUTDOWN';
                break;
              case 2:
                statusName = 'ON';
                break;
              case 3:
                statusName = 'CONNECTING';
                break;
              case 4:
                statusName = 'CONNECTED';
                break;
              case 5:
                statusName = 'TCP_CONNECTED';
                break;
              default:
                statusName = 'UNKNOWN';
                break;
            }
            debugPrint("SDCardWalSync WiFi: Device status: $statusName ($status)");
          },
        );
      } catch (e) {
        Logger.debug("SDCardWalSync WiFi: Failed to setup WiFi status listener: $e");
      }

      _downloadStartTime = DateTime.now();

      var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

      // Per-file data collection: keyed by TIMESTAMP (not index!).
      // Firmware sends files sequentially without deleting them. The 4-byte
      // timestamp embedded in every data packet is the stable unique key.
      Map<int, List<List<int>>> fileFrames = {}; // ts → frames
      Map<int, int> fileSizes = {}; // ts → expected bytes (from header)
      Map<int, int> fileReceivedBytes = {}; // ts → received bytes
      final Map<int, Wal> walByTimestamp = {for (final item in wals) item.timerStart: item};
      int? activeFileTs;
      int totalExpectedBytes = 0;
      int totalReceivedBytes = 0;

      var timerStart = wal.timerStart;

      // Cursor-based buffer: avoids O(N²) list copies for large transfers.
      List<int> tcpBuffer = [];
      int tcpBufPos = 0;
      bool headerParsed = false;

      // Firmware auto-starts WiFi sync after WIFI_START command (no BLE read needed)
      // Disconnect BLE before data transfer to free bandwidth
      debugPrint("SDCardWalSync WiFi: Disconnecting BLE before data transfer (expected)...");
      try {
        ServiceManager.instance().device.setWifiSyncInProgress(true);
        await ServiceManager.instance().device.disconnectDevice();
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: BLE disconnect error (non-fatal): $e");
      }
      connection = null;

      // Step 7: Receive and process data over WiFi
      debugPrint("SDCardWalSync WiFi: Step 7 - Receiving data over TCP");

      final completer = Completer<void>();
      _activeTransferCompleter = completer;
      StreamSubscription? audioSubscription;

      final audioStream = tcpTransport.dataStream;

      // Inactivity timer: if no data is received for 30 seconds, assume
      // the firmware has finished (or stalled) and complete the transfer.
      // This guards against byte-count mismatches that would otherwise
      // cause a hang until the 5-minute overall timeout.
      Timer? inactivityTimer;
      void resetInactivityTimer() {
        inactivityTimer?.cancel();
        inactivityTimer = Timer(const Duration(seconds: 30), () {
          if (!completer.isCompleted) {
            Logger.debug("SDCardWalSync WiFi: No data for 30s \u2014 completing transfer "
                "(received $totalReceivedBytes / $totalExpectedBytes bytes)");
            completer.complete();
          }
        });
      }

      audioSubscription = audioStream.listen(
        (List<int> value) {
          // Check for cancellation and complete immediately if cancelled
          if (_isCancelled) {
            if (!completer.isCompleted) {
              Logger.debug("SDCardWalSync WiFi: Transfer cancelled by user");
              completer.complete();
            }
            return;
          }
          if (completer.isCompleted) return;

          // Reset inactivity timer on every data chunk
          resetInactivityTimer();

          tcpBuffer.addAll(value);

          // Periodically compact the buffer to keep memory usage in check.
          if (tcpBufPos > 65536) {
            tcpBuffer = tcpBuffer.sublist(tcpBufPos);
            tcpBufPos = 0;
          }

          // Parse header first: [0xFF][count:1][ts1:4][sz1:4]...
          final int available = tcpBuffer.length - tcpBufPos;
          if (!headerParsed && available > 0 && tcpBuffer[tcpBufPos] == 0xFF) {
            if (available >= 2) {
              int fileCount = tcpBuffer[tcpBufPos + 1];
              int headerLen = 2 + fileCount * 8;
              if (available >= headerLen) {
                Logger.debug("SDCardWalSync WiFi: Parsing header: $fileCount files");
                for (int i = 0; i < fileCount; i++) {
                  int base = tcpBufPos + 2 + i * 8;
                  int ts = (tcpBuffer[base] << 24) |
                      (tcpBuffer[base + 1] << 16) |
                      (tcpBuffer[base + 2] << 8) |
                      tcpBuffer[base + 3];
                  int sz = (tcpBuffer[base + 4] << 24) |
                      (tcpBuffer[base + 5] << 16) |
                      (tcpBuffer[base + 6] << 8) |
                      tcpBuffer[base + 7];
                  fileSizes[ts] = sz;
                  totalExpectedBytes += sz;
                  Logger.debug("  File $i: ts=$ts, size=$sz");

                  final walForTs = walByTimestamp[ts];
                  if (walForTs != null && walForTs.storageTotalBytes <= 0) {
                    walForTs.storageTotalBytes = sz;
                  }
                }
                tcpBufPos += headerLen;
                headerParsed = true;
              } else {
                return; // Wait for more data
              }
            } else {
              return; // Wait for more data
            }
          }

          // Parse data packets: [idx:1][ts:4BE][len:2BE][data:len]
          // Key by TIMESTAMP extracted from bytes 1-4, not by idx byte 0.
          // Firmware resets idx to 0 after every file delete + list refresh, so
          // idx alone is ambiguous across multiple files.
          if (headerParsed) {
            while (tcpBuffer.length - tcpBufPos >= 7) {
              // Extract timestamp from packet header (bytes 1-4 after pos)
              int pktTs = (tcpBuffer[tcpBufPos + 1] << 24) |
                  (tcpBuffer[tcpBufPos + 2] << 16) |
                  (tcpBuffer[tcpBufPos + 3] << 8) |
                  tcpBuffer[tcpBufPos + 4];
              int dataLen = (tcpBuffer[tcpBufPos + 5] << 8) | tcpBuffer[tcpBufPos + 6];

              // Sanity check: dataLen must fit within remaining buffer
              if (dataLen <= 0 || dataLen > 8192) {
                Logger.debug("SDCardWalSync WiFi: Invalid dataLen=$dataLen, resetting buffer");
                tcpBufPos = tcpBuffer.length; // discard
                break;
              }

              if (tcpBuffer.length - tcpBufPos < 7 + dataLen) {
                break; // Wait for complete packet
              }

              var audioData = tcpBuffer.sublist(tcpBufPos + 7, tcpBufPos + 7 + dataLen);
              tcpBufPos += 7 + dataLen;

              // Parse packed opus frames: [size:1][frame:size]...
              if (!fileFrames.containsKey(pktTs)) {
                fileFrames[pktTs] = [];
              }
              var frameOffset = 0;
              while (frameOffset < audioData.length - 1) {
                var frameSize = audioData[frameOffset];
                if (frameSize == 0) {
                  frameOffset += 1;
                  continue;
                }
                if (frameOffset + 1 + frameSize > audioData.length) {
                  break;
                }
                var frame = audioData.sublist(frameOffset + 1, frameOffset + 1 + frameSize);
                fileFrames[pktTs]!.add(frame);
                frameOffset += frameSize + 1;
              }

              totalReceivedBytes += dataLen;
              fileReceivedBytes[pktTs] = (fileReceivedBytes[pktTs] ?? 0) + dataLen;

              final walForTs = walByTimestamp[pktTs];
              if (walForTs != null) {
                if (activeFileTs != pktTs) {
                  if (activeFileTs != null) {
                    final prevWal = walByTimestamp[activeFileTs!];
                    if (prevWal != null) {
                      prevWal.isSyncing = false;
                    }
                  }
                  activeFileTs = pktTs;
                  walForTs.syncStartedAt ??= DateTime.now();
                  walForTs.syncMethod = SyncMethod.wifi;
                }

                walForTs.isSyncing = true;
                final expectedForFile = fileSizes[pktTs] ?? walForTs.storageTotalBytes;
                if (expectedForFile > 0) {
                  final receivedForFile = fileReceivedBytes[pktTs] ?? 0;
                  walForTs.storageOffset = receivedForFile > expectedForFile ? expectedForFile : receivedForFile;
                }
              }
            }
          }

          // Update progress
          final (shouldUpdateProgress, shouldUpdateSpeed) = _updateWifiSpeed(value.length);

          if (shouldUpdateProgress || shouldUpdateSpeed) {
            final progressPercent =
                totalExpectedBytes > 0 ? (totalReceivedBytes / totalExpectedBytes).clamp(0.0, 1.0) : 0.0;

            if (shouldUpdateSpeed && _currentSpeedKBps > 0) {
              wal.syncSpeedKBps = _currentSpeedKBps;
              final bytesRemaining = totalExpectedBytes - totalReceivedBytes;
              wal.syncEtaSeconds = bytesRemaining > 0 ? (bytesRemaining / 1024 / _currentSpeedKBps).round() : 0;
            }

            progress?.onWalSyncedProgress(progressPercent, speedKBps: wal.syncSpeedKBps);
            listener.onWalUpdated();
          }

          // Check completion
          if (totalExpectedBytes > 0 && totalReceivedBytes >= totalExpectedBytes) {
            _finalizeWifiSpeed();
            wal.syncSpeedKBps = _currentSpeedKBps;
            wal.syncEtaSeconds = 0;
            progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
            listener.onWalUpdated();

            if (!completer.isCompleted) {
              inactivityTimer?.cancel();
              completer.complete();
            }
          }
        },
        onError: (error) {
          if (!completer.isCompleted) {
            inactivityTimer?.cancel();
            completer.completeError(error);
          }
        },
        onDone: () {
          if (!completer.isCompleted) {
            inactivityTimer?.cancel();
            completer.complete();
          }
        },
      );

      // Wait for transfer to complete
      try {
        await completer.future;
      } catch (e) {
        Logger.debug("SDCardWalSync WiFi: Transfer error: $e");
      }

      inactivityTimer?.cancel();

      final wasCancelled = _isCancelled;
      final allFilesComplete = fileSizes.isNotEmpty &&
          fileSizes.entries.every((entry) => (fileReceivedBytes[entry.key] ?? 0) >= entry.value);
      final fullyReceived = totalExpectedBytes > 0 && totalReceivedBytes >= totalExpectedBytes && allFilesComplete;

      if (!wasCancelled && !fullyReceived) {
        throw WifiSyncException(
          'WiFi transfer incomplete: received $totalReceivedBytes / $totalExpectedBytes bytes, '
          'filesComplete=$allFilesComplete',
        );
      }

      // Flush all collected data per file
      // entry.key IS the timestamp since we changed fileFrames to be ts-keyed.
      var chunkSize = sdcardChunkSizeSecs * wal.codec.getFramesPerSecond();
      for (var entry in fileFrames.entries) {
        int fileTimerStart = entry.key; // key is the unix timestamp
        var frames = entry.value;
        int bytesLeft = 0;

        while (frames.length - bytesLeft >= chunkSize) {
          var chunk = frames.sublist(bytesLeft, bytesLeft + chunkSize);
          bytesLeft += chunkSize;
          fileTimerStart += sdcardChunkSizeSecs;
          try {
            var file = await _flushToDisk(wal, chunk, fileTimerStart);
            await _registerSingleChunk(wal, file, fileTimerStart);
          } catch (e) {
            Logger.debug('SDCardWalSync WiFi: Error flushing chunk: $e');
          }
        }

        if (bytesLeft < frames.length) {
          var chunk = frames.sublist(bytesLeft);
          fileTimerStart += sdcardChunkSizeSecs;
          try {
            var file = await _flushToDisk(wal, chunk, fileTimerStart);
            await _registerSingleChunk(wal, file, fileTimerStart);
          } catch (e) {
            Logger.debug('SDCardWalSync WiFi: Error flushing final chunk: $e');
          }
        }
      }

      // Step 9: Cleanup
      inactivityTimer?.cancel();
      debugPrint("SDCardWalSync WiFi: Step 9 - Cleanup");
      _activeTcpTransport = null;
      _activeTransferCompleter = null;
      await audioSubscription.cancel();
      await wifiStatusSubscription?.cancel();

      try {
        await tcpTransport.disconnect();
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Error disconnecting TCP: $e");
      }

      try {
        await wifiNetwork.disconnectFromAp(ssid);
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Error disconnecting from AP: $e");
      }

      ServiceManager.instance().device.setWifiSyncInProgress(false);
      for (final item in wals) {
        item.isSyncing = false;
        item.syncStartedAt = null;
        item.syncEtaSeconds = null;
        item.syncSpeedKBps = null;
        item.syncMethod = SyncMethod.ble;
      }
      listener.onWalUpdated();
      _resetSyncState();

      if (wasCancelled) {
        debugPrint("SDCardWalSync WiFi: Cancelled - partial data saved, reconnecting BLE in background");
        DebugLogManager.logWarning('SD card WiFi sync cancelled', {
          'bytesTransferred': offset - initialOffset,
          'totalBytes': totalBytes,
        });
        // Reconnect BLE and stop WiFi sync in background
        _reconnectBleAfterCancel(deviceId);
        return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
      }

      // Reconnect BLE for cleanup
      DeviceConnection? bleConnection;
      try {
        await Future.delayed(const Duration(seconds: 2));
        bleConnection = await ServiceManager.instance().device.ensureConnection(deviceId);
        if (bleConnection != null) {
          debugPrint("SDCardWalSync WiFi: BLE reconnected for cleanup");
        }
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Could not reconnect BLE for cleanup: $e");
      }

      // Only mark as synced if transfer completed fully (not cancelled)
      // Firmware no longer auto-deletes: app deletes after confirming receipt
      if (!wasCancelled) {
        for (final ts in fileFrames.keys) {
          final syncedWal = walByTimestamp[ts];
          if (syncedWal != null) {
            syncedWal.status = WalStatus.synced;
            syncedWal.isSyncing = false;
            syncedWal.syncEtaSeconds = null;
            syncedWal.syncSpeedKBps = null;
          }
        }

        // Delete all synced files from firmware after successful WiFi transfer
        if (bleConnection != null) {
          try {
            Logger.debug("SDCardWalSync WiFi: Deleting synced files from firmware");
            // Re-list files and delete them all (they were all transferred)
            var files = await bleConnection.listFiles();
            // Delete in reverse order so indices don't shift
            for (var i = files.length - 1; i >= 0; i--) {
              bool deleted = await bleConnection.deleteFile(i);
              Logger.debug("SDCardWalSync WiFi: Delete file[$i] result: $deleted");
            }
          } catch (e) {
            Logger.debug("SDCardWalSync WiFi: Error deleting files after sync: $e (data is safe on phone)");
          }
        }
      } else {
        // Cancelled - partial data was saved as local WAL files
        debugPrint("SDCardWalSync WiFi: Cancelled - partial data saved, user can retry for remaining");
      }

      if (bleConnection != null) {
        try {
          await bleConnection.stopWifiSync();
        } catch (e) {
          debugPrint("SDCardWalSync WiFi: Error stopping WiFi on device: $e");
        }
      }

      return resp;
    } catch (e) {
      Logger.debug("SDCardWalSync WiFi: Error during sync: $e");
      DebugLogManager.logError(e, null, 'SD card WiFi sync error: ${e.toString()}');

      _activeTcpTransport = null;
      _activeTransferCompleter = null;
      ServiceManager.instance().device.setWifiSyncInProgress(false);

      // Reset WAL sync state on error
      for (final item in wals) {
        item.isSyncing = false;
        item.syncStartedAt = null;
        item.syncEtaSeconds = null;
        item.syncSpeedKBps = null;
        item.syncMethod = SyncMethod.ble;
      }
      listener.onWalUpdated();

      await _cleanupWifiSync(tcpTransport, wifiNetwork, ssid, connection, deviceId: deviceId);

      // Re-throw WifiSyncException as-is, wrap other exceptions
      if (e is WifiSyncException) {
        rethrow;
      } else {
        throw WifiSyncException(e.toString());
      }
    }
  }
}
