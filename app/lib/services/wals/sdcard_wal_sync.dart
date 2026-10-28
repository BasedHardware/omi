import 'package:omi/services/wals/local_wal_sync.dart';
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:version/version.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart' show walMinPlausibleTimerStartSeconds;

class SDCardWalSyncImpl implements SDCardWalSync {
  List<Wal> _wals = [];
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

  /// How far past "now" a device timestamp may sit and still count as a real
  /// clock: one day absorbs pendant clock skew without reopening the door to
  /// the years-away garbage that split real recordings into fragments.
  static const int _markerFutureToleranceSeconds = 24 * 60 * 60;

  /// Whether a decoded timestamp marker can name a real recording time. The
  /// window matches the backend's filename gate (>= 2024-01-01, not beyond
  /// now): once the packet walk desynchronizes, audio bytes decode as markers
  /// with garbage epochs — years in the future were rejected at upload as
  /// 1-second fragments, and garbage in the past uploaded silently under a
  /// wrong date. An implausible marker is ignored so the recording keeps the
  /// app-estimated clock instead of splitting.
  @visibleForTesting
  static bool markerEpochPlausible(int epoch, {DateTime? now}) {
    if (epoch < walMinPlausibleTimerStartSeconds) return false;
    final ceiling = (now ?? DateTime.now()).millisecondsSinceEpoch ~/ 1000 + _markerFutureToleranceSeconds;
    return epoch <= ceiling;
  }

  /// Parses an 83-byte SD card packet: byte 3 is the frame length, frame data starts at byte 4.
  /// Returns null when the length byte is corrupted (frame would exceed the packet bounds).
  /// Arms [duration] and cancels [previous]. A later packet or the initial 5s
  /// arm must not leave the earlier timer running, or it fires into a transfer
  /// that is still receiving data.
  @visibleForTesting
  static Timer replaceTimer(Timer? previous, Duration duration, void Function() onFire) {
    previous?.cancel();
    return Timer(duration, onFire);
  }

  static List<int>? parseLegacyPacketFrame(List<int> value) {
    final amount = value[3];
    if (amount <= 0 || 4 + amount > value.length) {
      return null;
    }
    return value.sublist(4, 4 + amount);
  }

  SDCardWalSyncImpl(this.listener);

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  @visibleForTesting
  set testDevice(BtDevice? device) => _device = device;

  DeviceConnection? _testConnection;

  @visibleForTesting
  set testConnection(DeviceConnection? connection) => _testConnection = connection;

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
    var connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  /// Delete a device recording. The wal leaves [_wals] only after the device
  /// confirmed the delete (command accepted AND storage readback shows the
  /// bytes gone); an unconfirmed delete — including when the owning device is
  /// absent or a different device is active — keeps the wal so the recording
  /// cannot resurrect as "new" on the next sync (fail-closed).
  @override
  Future deleteWal(Wal wal) async {
    if (wal.storage != WalStorage.sdcard || !_wals.any((w) => w.id == wal.id)) return;

    if (_device == null || wal.device != _device!.id) {
      Logger.debug("SDCardWalSync.deleteWal: owning device of ${wal.id} not connected, keeping WAL");
      return;
    }

    final confirmed = await _deleteOnDevice(wal);
    if (!confirmed) {
      Logger.debug("SDCardWalSync.deleteWal: device did not confirm deletion of ${wal.id}, keeping WAL");
      return;
    }

    _wals.removeWhere((w) => w.id == wal.id);
    listener.onWalUpdated();
  }

  /// Send the delete command for [wal] and verify it took effect: read the
  /// storage list back and require totalBytes to have dropped below the
  /// wal's discovered size. `writeToStorage` returning true only means the
  /// BLE write was accepted — the readback is what proves the audio is gone.
  /// An empty readback is ambiguous (no connection vs. empty card) and
  /// counts as unconfirmed.
  Future<bool> _deleteOnDevice(Wal wal) async {
    final ok = await _writeToStorage(_device!.id, wal.fileNum, 1, 0);
    if (!ok) return false;
    final storageFiles = await _getStorageList(_device!.id);
    if (storageFiles.isEmpty) return false;
    return storageFiles[0] < wal.storageTotalBytes;
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

    final BleAudioCodec codec;
    try {
      codec = await _getAudioCodec(deviceId);
    } catch (e) {
      Logger.debug('SDCardWalSync: failed to get audio codec, skipping listing: ');
      return [];
    }
    if (totalBytes - storageOffset > 10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
      var seconds = ((totalBytes - storageOffset) / codec.getFramesLengthInBytes()) ~/ codec.getFramesPerSecond();
      // Use device-provided recording start timestamp if available (firmware >= 3.0.16), otherwise estimate
      int timerStart;
      String? clockRun;
      final listedStart = storageFiles.length >= 3 ? storageFiles[2] : 0;
      if (_supportsTimestampMarkers() && markerEpochPlausible(listedStart)) {
        timerStart = listedStart;
      } else {
        if (listedStart > 0) {
          DebugLogManager.logEvent('implausible_timestamp_marker_ignored', {'epoch': listedStart, 'source': 'listing'});
        }
        timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - seconds;
        clockRun = Wal.newClockRun();
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
          clockRun: clockRun,
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
    var connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(false);
    }
    return connection.writeToStorage(numFile, command, offset);
  }

  Future<StreamSubscription?> _getBleStorageBytesListener(
    String deviceId, {
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    var connection = _testConnection ?? await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleStorageBytesListener(onStorageBytesReceived: onStorageBytesReceived);
  }

  int _storageFileSeq = 0;
  int _admittedGeneration = -1;

  /// Non-null while the chunks being flushed carry an app-estimated start
  /// time; see [Wal.clockRun]. A device timestamp marker clears it.
  String? _activeClockRun;

  Future<File> _flushToDisk(Wal wal, List<List<int>> chunk, int timerStart) async {
    final localSync = _localSync;
    if (localSync == null) throw StateError('LocalWalSync unavailable; chunk cannot be proven durable');
    final saved = await localSync.persistDeviceChunk(
        source: wal,
        frames: chunk,
        timerStart: timerStart,
        admittedGeneration: _admittedGeneration,
        clockRun: _activeClockRun,
        nextCollisionSequence: () => _storageFileSeq++);
    return File((await Wal.getFilePath(saved.filePath))!);
  }

  Future<bool> _readStorageBytesToFile(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback,
  ) async {
    if (_supportsTimestampMarkers()) {
      return _readStorageBytesToFileWithMarkers(wal, callback);
    }
    return _readStorageBytesToFileLegacy(wal, callback);
  }

  Future<bool> _readStorageBytesToFileLegacy(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback,
  ) async {
    var deviceId = wal.device;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;

    Logger.debug("_readStorageBytesToFileLegacy $offset");

    List<List<int>> bytesData = [];
    var chunkSize = sdcardChunkSizeSecs * 100;
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    bool hasError = false;
    bool sawEndSignal = false;
    bool parseGap = false;
    bool firstDataReceived = false;
    Timer? timeoutTimer;

    _storageStream = await _getBleStorageBytesListener(
      deviceId,
      onStorageBytesReceived: (List<int> value) {
        if (value.isEmpty || hasError || completer.isCompleted) return;

        if (!firstDataReceived) {
          firstDataReceived = true;
          timeoutTimer?.cancel();
          Logger.debug('First data received, timeout cancelled');
        }
        timeoutTimer = replaceTimer(timeoutTimer, const Duration(seconds: 15), () {
          if (!completer.isCompleted) {
            hasError = true;
            Logger.debug('SD card read stalled: no data for 15s');
            completer.completeError(TimeoutException('SD card read stalled'));
          }
        });

        if (value.length == 1) {
          Logger.debug('returned $value');
          if (value[0] == 0) {
            Logger.debug('good to go');
          } else if (value[0] == 3) {
            Logger.debug('bad file size. finishing...');
            hasError = true;
            if (!completer.isCompleted) completer.complete(false);
          } else if (value[0] == 4) {
            Logger.debug('file size is zero. going to next one....');
            sawEndSignal = true;
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else if (value[0] == 100) {
            Logger.debug('end');
            sawEndSignal = true;
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else {
            Logger.debug('Error bit returned');
            hasError = true;
            if (!completer.isCompleted) {
              completer.complete(false);
            }
          }
          return;
        }

        if (value.length == 83) {
          final frame = parseLegacyPacketFrame(value);
          if (frame != null) {
            bytesData.add(frame);
          } else {
            Logger.debug('Skipping corrupted SD card packet: invalid frame length ${value[3]}');
            parseGap = true;
          }
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
        } else {
          parseGap = true;
        }
      },
    );

    await _writeToStorage(deviceId, fileNum, 0, offset);

    timeoutTimer = replaceTimer(timeoutTimer, const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        hasError = true;
        final error = TimeoutException('No data received from SD card within 5 seconds');
        Logger.debug('SD card read timeout: ${error.message}');
        DebugLogManager.logWarning('SD card BLE read timeout: no data in 5s', {'offset': offset});
        completer.completeError(error);
      }
    });

    bool sawEnd = false;
    try {
      sawEnd = await completer.future;
    } catch (e) {
      rethrow;
    } finally {
      await _storageStream?.cancel();
      timeoutTimer?.cancel();
    }

    // After download: compute accurate duration from actual frame count
    if (!hasError && bytesData.isNotEmpty) {
      int totalFrames = bytesData.length;
      int accurateDuration = totalFrames ~/ wal.codec.getFramesPerSecond();
      // This firmware stores no recording time: every chunk's start is an estimate.
      int timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - accurateDuration;
      _activeClockRun = wal.clockRun ?? Wal.newClockRun();

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
          rethrow;
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

    final expectedEnd = wal.storageTotalBytes;
    final offsetReached = expectedEnd <= 0 || offset >= expectedEnd;
    return sawEnd && sawEndSignal && offsetReached && !hasError && !parseGap && !_isCancelled;
  }

  Future<bool> _readStorageBytesToFileWithMarkers(
    Wal wal,
    Function(File f, int offset, int timerStart, int chunkFrames) callback,
  ) async {
    var deviceId = wal.device;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;
    int timerStart = wal.timerStart;
    // Estimated until the first device timestamp marker, unless the listing
    // already supplied the device's recording start.
    _activeClockRun = wal.clockRun;

    Logger.debug("_readStorageBytesToFileWithMarkers $offset");

    List<List<int>> bytesData = [];
    var bytesLeft = 0;
    var chunkSize = sdcardChunkSizeSecs * wal.codec.getFramesPerSecond();
    List<MapEntry<int, int>> timestampMarkers = [];
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    bool hasError = false;
    bool sawEndSignal = false;
    bool parseGap = false;
    bool firstDataReceived = false;
    Timer? timeoutTimer;

    Future<void> cbQueue = Future.value();

    _storageStream = await _getBleStorageBytesListener(
      deviceId,
      onStorageBytesReceived: (List<int> value) {
        if (value.isEmpty || hasError || completer.isCompleted) return;

        if (!firstDataReceived) {
          firstDataReceived = true;
          timeoutTimer?.cancel();
          Logger.debug('First data received, timeout cancelled');
        }
        timeoutTimer = replaceTimer(timeoutTimer, const Duration(seconds: 15), () {
          if (!completer.isCompleted) {
            hasError = true;
            Logger.debug('SD card read stalled: no data for 15s');
            completer.completeError(TimeoutException('SD card read stalled'));
          }
        });

        if (value.length == 1) {
          Logger.debug('returned $value');
          if (value[0] == 0) {
            Logger.debug('good to go');
          } else if (value[0] == 3) {
            Logger.debug('bad file size. finishing...');
            hasError = true;
            if (!completer.isCompleted) completer.complete(false);
          } else if (value[0] == 4) {
            Logger.debug('file size is zero. going to next one....');
            sawEndSignal = true;
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else if (value[0] == 100) {
            Logger.debug('end');
            sawEndSignal = true;
            if (!completer.isCompleted) {
              completer.complete(true);
            }
          } else {
            Logger.debug('Error bit returned');
            hasError = true;
            if (!completer.isCompleted) {
              completer.complete(false);
            }
          }
          return;
        }

        if (value.length == 83) {
          final frame = parseLegacyPacketFrame(value);
          if (frame != null) {
            bytesData.add(frame);
          } else {
            Logger.debug('Skipping corrupted SD card packet: invalid frame length ${value[3]}');
            parseGap = true;
          }
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
              if (markerEpochPlausible(epoch)) {
                timestampMarkers.add(MapEntry(bytesData.length, epoch));
                Logger.debug('Timestamp marker: epoch=$epoch at frame ${bytesData.length}');
              } else {
                // Audio bytes that decoded like a marker: ignoring it keeps the
                // estimated clock and the recording whole instead of splitting
                // it into fragments dated years away.
                DebugLogManager.logEvent('implausible_timestamp_marker_ignored', {'epoch': epoch});
                Logger.debug('Ignored implausible timestamp marker: epoch=$epoch');
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
        } else {
          parseGap = true;
        }

        cbQueue = cbQueue.then((_) async {
          if (hasError) return;
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
              rethrow;
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
                rethrow;
              }
              timerStart += chunkSecs;
            } else {
              bytesLeft = nextMarkerIdx;
            }
            // Apply the marker's epoch
            for (var m in timestampMarkers) {
              if (m.key == nextMarkerIdx) {
                timerStart = m.value;
                _activeClockRun = null;
                break;
              }
            }
          }
        }).catchError((_) {});
      },
    );

    await _writeToStorage(deviceId, fileNum, 0, offset);

    timeoutTimer = replaceTimer(timeoutTimer, const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        hasError = true;
        final error = TimeoutException('No data received from SD card within 5 seconds');
        Logger.debug('SD card read timeout: ${error.message}');
        DebugLogManager.logWarning('SD card BLE read timeout: no data in 5s', {'offset': offset});
        completer.completeError(error);
      }
    });

    bool sawEnd = false;
    try {
      sawEnd = await completer.future;
    } catch (e) {
      rethrow;
    } finally {
      await _storageStream?.cancel();
      timeoutTimer?.cancel();
      await cbQueue;
    }

    // Flush remaining data, respecting any unprocessed timestamp markers
    if (!hasError && bytesLeft < bytesData.length) {
      List<List<int>> segments = [];
      int segStart = bytesLeft;
      int segEpoch = timerStart;
      // 1 when the segment starts at a device marker, 0 when it continues the
      // current (possibly estimated) clock.
      int segMarked = 0;
      for (var marker in timestampMarkers) {
        if (marker.key > bytesLeft && marker.key < bytesData.length) {
          if (marker.key > segStart) {
            segments.add([segStart, marker.key, segEpoch, segMarked]);
          }
          segStart = marker.key;
          segEpoch = marker.value;
          segMarked = 1;
        }
      }
      if (segStart < bytesData.length) {
        segments.add([segStart, bytesData.length, segEpoch, segMarked]);
      }

      for (var seg in segments) {
        int sStart = seg[0];
        int sEnd = seg[1];
        int sEpoch = seg[2];
        if (seg[3] == 1) _activeClockRun = null;
        var chunk = bytesData.sublist(sStart, sEnd);
        var chunkFrames = chunk.length;
        if (chunkFrames > 0) {
          var file = await _flushToDisk(wal, chunk, sEpoch);
          await callback(file, offset, sEpoch, chunkFrames);
        }
      }
    }

    final expectedEnd = wal.storageTotalBytes;
    final offsetReached = expectedEnd <= 0 || offset >= expectedEnd;
    return sawEnd && sawEndSignal && offsetReached && !hasError && !parseGap && !_isCancelled;
  }

  Future<SyncLocalFilesResponse> _syncWal(final Wal wal, Function(int offset, double speedKBps)? updates) async {
    Logger.debug("SDCard sync (two-phase): ${wal.id} byte offset: ${wal.storageOffset} ts ${wal.timerStart}");

    if (_localSync == null) {
      Logger.debug("SDCard: ERROR - LocalWalSync not available, aborting to preserve data safety");
      DebugLogManager.logError('SD card sync aborted: LocalWalSync not available', null, null);
      throw Exception('Local sync service not available. Cannot safely download SD card data.');
    }

    final admittedGeneration = _localSync!.sessionGeneration;
    _admittedGeneration = admittedGeneration;

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

    bool readComplete = false;
    try {
      readComplete = await _readStorageBytesToFile(wal, (File file, int offset, int timerStart, int chunkFrames) async {
        if (_isCancelled) {
          throw Exception('Sync cancelled by user');
        }

        int bytesInChunk = offset - lastOffset;
        _updateSpeed(bytesInChunk);
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

    if (!readComplete) {
      Logger.debug('SDCard: read incomplete — leaving card contents intact');
      throw StateError('SD card read incomplete; refusing to clear');
    }
    Logger.debug("SDCard Phase 3: Clearing SD card storage");
    final cleared = await _writeToStorage(wal.device, wal.fileNum, 1, 0);
    if (!cleared) {
      Logger.debug('SDCard: CLEAR not acknowledged — leaving wal as miss');
      throw StateError('SD card clear not acknowledged');
    }

    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
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
          wal.syncSpeedKBps = speedKBps;

          final bytesRemaining = wal.storageTotalBytes - offset;
          if (speedKBps > 0) {
            wal.syncEtaSeconds = (bytesRemaining / 1024 / speedKBps).round();
          }

          final bytesDownloaded = offset - storageOffsetStarts;
          final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;
          wal.deviceDownloadFraction = progressPercent.clamp(0.0, 1.0);

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
        wal.deviceDownloadFraction = null;
        wal.syncMethod = SyncMethod.ble;
        listener.onWalUpdated();
        _resetSyncState();
        rethrow;
      }

      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      wal.deviceDownloadFraction = null;
      wal.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();
    }

    _resetSyncState();
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    // setDevice() and start() rebuild _wals with new Wal objects on every
    // connection, so a recording page opened before a reconnect holds an object
    // that is no longer listed. Match by id, as deleteWal does, and by storage,
    // because a phone copy of the recording can share its id.
    var walToSync = _wals.where((w) => w.storage == wal.storage && w.id == wal.id).firstOrNull;
    if (walToSync == null) {
      Logger.debug("SDCardWalSync: WAL not found in _wals, skipping sync");
      // Transfer to Phone reports any normal return as a completed transfer.
      throw Exception('Device recording list changed; go back and try again');
    }

    _resetSyncState();
    _isSyncing = true;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    walToSync.syncMethod = SyncMethod.ble;
    listener.onWalUpdated();

    final storageOffsetStarts = walToSync.storageOffset;
    final totalBytes = walToSync.storageTotalBytes - storageOffsetStarts;

    try {
      var partialRes = await _syncWal(walToSync, (offset, speedKBps) {
        walToSync.syncSpeedKBps = speedKBps;

        final bytesRemaining = walToSync.storageTotalBytes - offset;
        if (speedKBps > 0) {
          walToSync.syncEtaSeconds = (bytesRemaining / 1024 / speedKBps).round();
        }

        final bytesDownloaded = offset - storageOffsetStarts;
        final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;
        walToSync.deviceDownloadFraction = progressPercent.clamp(0.0, 1.0);

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

      walToSync.status = WalStatus.synced;
    } catch (e) {
      Logger.debug("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
      DebugLogManager.logError(e, null, 'SD card single WAL sync failed: ${e.toString()}', {'walId': wal.id});
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      walToSync.syncSpeedKBps = null;
      walToSync.deviceDownloadFraction = null;
      walToSync.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();
      _resetSyncState();
      rethrow;
    }

    walToSync.isSyncing = false;
    walToSync.syncStartedAt = null;
    walToSync.syncEtaSeconds = null;
    walToSync.syncSpeedKBps = null;
    walToSync.deviceDownloadFraction = null;
    walToSync.syncMethod = SyncMethod.ble;

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
