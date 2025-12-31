import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wifi_audio_receiver.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String _wifiSsidKey = 'wifi_sync_ssid';
const String _wifiPasswordKey = 'wifi_sync_password';

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

  // WiFi sync fields
  String? _wifiSsid;
  String? _wifiPassword;

  SDCardWalSyncImpl(this.listener);

  @override
  void setLocalSync(LocalWalSync localSync) {
    _localSync = localSync;
  }

  @override
  void cancelSync() {
    if (_isSyncing) {
      _isCancelled = true;
      debugPrint("SDCardWalSync: Cancel requested");
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
    _totalBytesDownloaded = 0;
    _downloadStartTime = null;
    _currentSpeedKBps = 0.0;
    _smoothedSpeedKBps = 0.0;
    _wifiSpeedSamples.clear();
    _wifiSpeedTimestamps.clear();
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

  // Rolling window for WiFi speed calculation (more accurate for high-speed transfers)
  List<int> _wifiSpeedSamples = [];
  List<DateTime> _wifiSpeedTimestamps = [];
  static const int _maxWifiSpeedSamples = 50;
  static const double _speedSmoothingFactor = 0.3;
  double _smoothedSpeedKBps = 0.0;

  void _updateWifiSpeed(int bytesDownloaded) {
    _totalBytesDownloaded += bytesDownloaded;
    final now = DateTime.now();

    // Add new sample
    _wifiSpeedSamples.add(bytesDownloaded);
    _wifiSpeedTimestamps.add(now);

    // Keep only last N samples
    while (_wifiSpeedSamples.length > _maxWifiSpeedSamples) {
      _wifiSpeedSamples.removeAt(0);
      _wifiSpeedTimestamps.removeAt(0);
    }

    // Calculate speed from rolling window
    if (_wifiSpeedSamples.length >= 2) {
      final windowBytes = _wifiSpeedSamples.fold<int>(0, (sum, b) => sum + b);
      final windowDuration = _wifiSpeedTimestamps.last.difference(_wifiSpeedTimestamps.first);
      final windowSeconds = windowDuration.inMilliseconds / 1000.0;

      if (windowSeconds > 0.2) {
        final rawSpeed = (windowBytes / 1024) / windowSeconds;
        // Apply exponential moving average for smoother display
        if (_smoothedSpeedKBps == 0.0) {
          _smoothedSpeedKBps = rawSpeed;
        } else {
          _smoothedSpeedKBps = (_speedSmoothingFactor * rawSpeed) + ((1 - _speedSmoothingFactor) * _smoothedSpeedKBps);
        }
        _currentSpeedKBps = _smoothedSpeedKBps;
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
      debugPrint("SDCard bad state, offset > total");
      storageOffset = 0;
    }

    BleAudioCodec codec = await _getAudioCodec(deviceId);
    if (totalBytes - storageOffset > 10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
      var seconds = ((totalBytes - storageOffset) / codec.getFramesLengthInBytes()) ~/ codec.getFramesPerSecond();
      var timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - seconds;

      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      var pd = await _device!.getDeviceInfo(connection);
      String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";

      wals.add(Wal(
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
      ));
    }

    return wals;
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
  }

  @override
  Future start() async {
    _wals = await _getMissingWals();
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
      debugPrint(
          "SDCardWalSync _flushToDisk: ${chunk.length} frames, first frame size=${firstFrame.length}, hex: $frameHex");
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

    debugPrint("SDCardWalSync _flushToDisk: Wrote ${data.length} bytes to $filePath");

    return file;
  }

  Future _readStorageBytesToFile(Wal wal, Function(File f, int offset, int timerStart) callback) async {
    var deviceId = wal.device;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;
    int timerStart = wal.timerStart;

    debugPrint("_readStorageBytesToFile ${offset}");

    List<List<int>> bytesData = [];
    var bytesLeft = 0;
    var chunkSize = sdcardChunkSizeSecs * 100;
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    bool hasError = false;
    bool firstDataReceived = false;
    Timer? timeoutTimer;

    _storageStream = await _getBleStorageBytesListener(deviceId, onStorageBytesReceived: (List<int> value) async {
      if (value.isEmpty || hasError) return;

      if (!firstDataReceived) {
        firstDataReceived = true;
        timeoutTimer?.cancel();
        debugPrint('First data received, timeout cancelled');
      }

      if (value.length == 1) {
        debugPrint('returned $value');
        if (value[0] == 0) {
          debugPrint('good to go');
        } else if (value[0] == 3) {
          debugPrint('bad file size. finishing...');
        } else if (value[0] == 4) {
          debugPrint('file size is zero. going to next one....');
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        } else if (value[0] == 100) {
          debugPrint('end');
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        } else {
          debugPrint('Error bit returned');
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

      if (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        timerStart += sdcardChunkSizeSecs;
        try {
          var file = await _flushToDisk(wal, chunk, timerStart);
          await callback(file, offset, timerStart);
        } catch (e) {
          debugPrint('Error in callback during chunking: $e');
          hasError = true;
          if (!completer.isCompleted) {
            completer.completeError(e);
          }
        }
      }
    });

    await _writeToStorage(deviceId, fileNum, 0, offset);

    timeoutTimer = Timer(const Duration(seconds: 5), () {
      if (!firstDataReceived && !completer.isCompleted) {
        hasError = true;
        final error = TimeoutException('No data received from SD card within 5 seconds');
        debugPrint('SD card read timeout: ${error.message}');
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

    if (!hasError && bytesLeft < bytesData.length - 1) {
      var chunk = bytesData.sublist(bytesLeft);
      timerStart += sdcardChunkSizeSecs;
      var file = await _flushToDisk(wal, chunk, timerStart);
      await callback(file, offset, timerStart);
    }

    return;
  }

  Future<SyncLocalFilesResponse> _syncWal(final Wal wal, Function(int offset, double speedKBps)? updates) async {
    debugPrint("SDCard sync (two-phase): ${wal.id} byte offset: ${wal.storageOffset} ts ${wal.timerStart}");

    if (_localSync == null) {
      debugPrint("SDCard: ERROR - LocalWalSync not available, aborting to preserve data safety");
      throw Exception('Local sync service not available. Cannot safely download SD card data.');
    }

    int chunksDownloaded = 0;
    int lastOffset = wal.storageOffset;
    int totalBytesToDownload = wal.storageTotalBytes - wal.storageOffset;

    debugPrint("SDCard Phase 1: Downloading ~${(totalBytesToDownload / 1024).toStringAsFixed(1)} KB to phone storage");

    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    try {
      await _readStorageBytesToFile(wal, (File file, int offset, int timerStart) async {
        if (_isCancelled) {
          throw Exception('Sync cancelled by user');
        }

        int bytesInChunk = offset - lastOffset;
        _updateSpeed(bytesInChunk);
        await _registerSingleChunk(wal, file, timerStart);
        chunksDownloaded++;
        lastOffset = offset;

        listener.onWalUpdated();
        if (updates != null) {
          updates(offset, _currentSpeedKBps);
        }

        debugPrint(
            "SDCard: Chunk $chunksDownloaded downloaded (ts: $timerStart, speed: ${_currentSpeedKBps.toStringAsFixed(1)} KB/s)");
      });
    } catch (e) {
      await _storageStream?.cancel();
      debugPrint('SDCard download failed: $e');
      if (chunksDownloaded > 0) {
        debugPrint("SDCard: $chunksDownloaded chunks saved before failure");
      }
      rethrow;
    }

    if (chunksDownloaded == 0) {
      debugPrint("SDCard: No chunks downloaded");
      return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    }

    debugPrint("SDCard Phase 1 complete: $chunksDownloaded chunks downloaded");

    debugPrint("SDCard Phase 3: Clearing SD card storage");
    await _writeToStorage(wal.device, wal.fileNum, 1, 0);

    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  Future<void> _registerSingleChunk(Wal wal, File file, int timerStart) async {
    if (_localSync == null) {
      debugPrint("SDCard: WARNING - Cannot register chunk, LocalWalSync not available");
      return;
    }

    int chunkSeconds = sdcardChunkSizeSecs;

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
      totalFrames: chunkSeconds * wal.codec.getFramesPerSecond(),
      syncedFrameOffset: 0,
      originalStorage: WalStorage.sdcard,
    );

    await _localSync!.addExternalWal(localWal);
    debugPrint(
        "SDCard: Registered chunk (ts: $timerStart) with LocalWalSync - codec=${localWal.codec}, sampleRate=${localWal.sampleRate}, channel=${localWal.channel}");
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) {
      debugPrint("SDCardWalSync: All synced!");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    for (var i = wals.length - 1; i >= 0; i--) {
      if (_isCancelled) {
        debugPrint("SDCardWalSync: Sync cancelled before processing WAL ${wals[i].id}");
        break;
      }

      var wal = wals[i];

      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
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

        resp.newConversationIds
            .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

        wal.status = WalStatus.synced;
      } catch (e) {
        debugPrint("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
        wal.isSyncing = false;
        wal.syncStartedAt = null;
        wal.syncEtaSeconds = null;
        wal.syncSpeedKBps = null;
        listener.onWalUpdated();
        _resetSyncState();
        rethrow;
      }

      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      listener.onWalUpdated();
    }

    _resetSyncState();
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    var walToSync = _wals.where((w) => w == wal).toList().first;

    _resetSyncState();
    _isSyncing = true;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
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

      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

      wal.status = WalStatus.synced;
    } catch (e) {
      debugPrint("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;
      listener.onWalUpdated();
      _resetSyncState();
      rethrow;
    }

    wal.isSyncing = false;
    wal.syncStartedAt = null;
    wal.syncEtaSeconds = null;
    wal.syncSpeedKBps = null;

    listener.onWalUpdated();
    _resetSyncState();
    return resp;
  }

  @override
  void setDevice(BtDevice? device) async {
    _device = device;
    _wals = await _getMissingWals();
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
  Future<bool> isWifiSyncSupported() async {
    if (_device == null) {
      debugPrint("SDCardWalSync WiFi: No device connected");
      return false;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) {
      debugPrint("SDCardWalSync WiFi: Could not get device connection");
      return false;
    }
    final supported = await connection.isWifiSyncSupported();

    final hasCredentials = _wifiSsid != null && _wifiSsid!.isNotEmpty;

    return supported && hasCredentials;
  }

  @override
  Future<bool> setWifiCredentials(String ssid, String password) async {
    _wifiSsid = ssid;
    _wifiPassword = password;

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_wifiSsidKey, ssid);
      await prefs.setString(_wifiPasswordKey, password);
      debugPrint("SDCardWalSync: WiFi credentials saved for SSID: $ssid");
      return true;
    } catch (e) {
      debugPrint("SDCardWalSync: Failed to save WiFi credentials: $e");
      return false;
    }
  }

  @override
  Future<void> clearWifiCredentials() async {
    _wifiSsid = null;
    _wifiPassword = null;

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_wifiSsidKey);
    await prefs.remove(_wifiPasswordKey);
  }

  @override
  Future<void> loadWifiCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    _wifiSsid = prefs.getString(_wifiSsidKey);
    _wifiPassword = prefs.getString(_wifiPasswordKey);
    if (_wifiSsid != null) {
      debugPrint("SDCardWalSync: Loaded WiFi credentials for SSID: $_wifiSsid");
    }
  }

  @override
  Map<String, String?>? getWifiCredentials() {
    if (_wifiSsid == null) return null;
    return {'ssid': _wifiSsid, 'password': _wifiPassword};
  }

  @override
  Future<SyncLocalFilesResponse?> syncWithWifi({IWalSyncProgressListener? progress}) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) {
      debugPrint("SDCardWalSync WiFi: All synced!");
      return null;
    }

    if (_device == null) {
      debugPrint("SDCardWalSync WiFi: No device connected");
      return null;
    }

    if (_wifiSsid == null || _wifiPassword == null) {
      debugPrint("SDCardWalSync WiFi: No WiFi credentials set");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    // Get device connection
    var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) {
      debugPrint("SDCardWalSync WiFi: Failed to get device connection");
      _resetSyncState();
      return null;
    }

    // Get the WiFi receiver singleton
    final wifiReceiver = WifiAudioReceiver.instance;

    try {
      // Get local IP address for the TCP server
      final localIp = await wifiReceiver.getLocalIpAddress();
      if (localIp == null) {
        debugPrint("SDCardWalSync WiFi: Could not determine local IP address");
        await wifiReceiver.stop();
        _resetSyncState();
        throw Exception('WiFi sync failed: Please enable your phone\'s hotspot and try again');
      }

      const tcpPort = WifiAudioReceiver.defaultPort;

      // Start TCP server
      final serverStarted = await wifiReceiver.start(port: tcpPort);
      if (!serverStarted) {
        await wifiReceiver.stop();
        _resetSyncState();
        throw Exception('WiFi sync failed: Failed to start TCP server');
      }

      // Step 1: Setup WiFi on device with credentials and server info
      final setupSuccess = await connection.setupWifiSync(_wifiSsid!, _wifiPassword!, localIp, tcpPort);
      if (!setupSuccess) {
        await wifiReceiver.stop();
        _resetSyncState();
        throw Exception('WiFi sync failed: Failed to setup WiFi on device');
      }

      // Wait for the device to process the setup command
      await Future.delayed(const Duration(seconds: 1));

      // Step 2: Start WiFi transfer on device
      final startSuccess = await connection.startWifiSync();
      if (!startSuccess) {
        await wifiReceiver.stop();
        _resetSyncState();
        return null;
      }

      StreamSubscription? wifiStatusSubscription;
      int lastWifiStatus = -1;
      try {
        wifiStatusSubscription = await connection.getWifiSyncStatusListener(
          onStatusReceived: (status) {
            if (status != lastWifiStatus) {
              lastWifiStatus = status;
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
            }
          },
        );
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Failed to setup WiFi status listener: $e");
      }

      _downloadStartTime = DateTime.now();

      var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

      final wal = wals.last;
      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
      listener.onWalUpdated();

      List<List<int>> bytesData = [];
      var bytesLeft = 0;
      var chunkSize = sdcardChunkSizeSecs * wal.codec.getFramesPerSecond();
      var timerStart = wal.timerStart;

      final initialOffset = wal.storageOffset;
      var offset = wal.storageOffset;
      final totalBytes = wal.storageTotalBytes - initialOffset;

      List<int> tcpBuffer = [];

      final completer = Completer<void>();
      StreamSubscription? audioSubscription;

      final audioStream = wifiReceiver.audioStream;
      if (audioStream == null) {
        debugPrint("SDCardWalSync WiFi: No TCP client connected");
        await wifiStatusSubscription?.cancel();
        await wifiReceiver.stop();
        _resetSyncState();
        throw Exception(
            'WiFi sync failed: Device could not connect to hotspot. Check WiFi credentials and ensure hotspot is active.');
      }

      final readStarted = await _writeToStorage(_device!.id, wal.fileNum, 0, offset);
      if (!readStarted) {
        await wifiReceiver.stop();
        await connection.stopWifiSync();
        _resetSyncState();
        throw Exception('WiFi sync failed: Failed to start storage read');
      }

      // Track position within 440-byte logical blocks
      // The SD card data is organized in 440-byte chunks, same as BLE packets
      // Each chunk may have padding at the end that shouldn't be parsed as frame data
      int globalBytePosition = 0;

      audioSubscription = audioStream.listen(
        (List<int> value) {
          if (_isCancelled || completer.isCompleted) return;

          tcpBuffer.addAll(value);

          final bufferLength = tcpBuffer.length;

          // Process the buffer - format: [size1][data1][size2][data2]...
          // Data is organized in 440-byte logical blocks
          var packageOffset = 0;
          var bytesProcessed = 0;

          while (packageOffset < bufferLength) {
            var packageSize = tcpBuffer[packageOffset];

            // Calculate position within current 440-byte block
            int posInBlock = (globalBytePosition + packageOffset) % 440;
            int bytesRemainingInBlock = 440 - posInBlock;

            // Skip zero-size markers
            if (packageSize == 0) {
              packageOffset += 1;
              bytesProcessed = packageOffset;
              continue;
            }

            // Check if we're in padding area at end of block
            // If we're near end of block and size seems invalid, skip to next block
            if (posInBlock > 0 && bytesRemainingInBlock < 12) {
              // Not enough room for a minimal frame (size + 10 byte min data)
              // Skip padding to next block boundary
              if (packageOffset + bytesRemainingInBlock > bufferLength) {
                break; // Wait for more data
              }

              packageOffset += bytesRemainingInBlock;
              bytesProcessed = packageOffset;
              continue;
            }

            // Check if this frame would extend beyond the current 440-byte block boundary
            // SD card frames never span block boundaries - if it would, this is padding
            if (posInBlock > 0 && packageSize + 1 > bytesRemainingInBlock) {
              // Frame doesn't fit in current block, skip to next boundary
              if (packageOffset + bytesRemainingInBlock > bufferLength) {
                break; // Wait for more data
              }

              packageOffset += bytesRemainingInBlock;
              bytesProcessed = packageOffset;
              continue;
            }

            if (packageSize > 160 || packageSize < 10) {
              if (posInBlock == 0) {
                packageOffset += 1;
                bytesProcessed = packageOffset;
              } else if (bytesRemainingInBlock > 0 && packageOffset + bytesRemainingInBlock <= bufferLength) {
                packageOffset += bytesRemainingInBlock;
                bytesProcessed = packageOffset;
              } else {
                break; // Wait for more data
              }
              continue;
            }

            // Check if we have the complete frame (size byte + frame data)
            if (packageOffset + 1 + packageSize > bufferLength) {
              // Incomplete frame - wait for more data
              break;
            }

            // Extract complete frame
            var frame = tcpBuffer.sublist(packageOffset + 1, packageOffset + 1 + packageSize);

            bool validToc = frame.isNotEmpty &&
                (frame[0] == 0xb8 ||
                    frame[0] == 0xb0 ||
                    frame[0] == 0xbc ||
                    frame[0] == 0xf8 ||
                    frame[0] == 0xfc ||
                    frame[0] == 0x78 ||
                    frame[0] == 0x7c);

            if (!validToc) {
              // Skip to next block boundary
              if (posInBlock > 0 && packageOffset + bytesRemainingInBlock <= bufferLength) {
                packageOffset += bytesRemainingInBlock;
                bytesProcessed = packageOffset;
              } else {
                packageOffset += packageSize + 1;
                bytesProcessed = packageOffset;
              }
              continue;
            }

            bytesData.add(frame);

            packageOffset += packageSize + 1;
            bytesProcessed = packageOffset;
          }

          // Update global position for block tracking
          globalBytePosition += bytesProcessed;

          // Remove processed bytes from buffer safely
          if (bytesProcessed > 0) {
            // Create new list from unprocessed bytes
            tcpBuffer = List<int>.from(tcpBuffer.skip(bytesProcessed));
          }

          offset += value.length;
          _updateWifiSpeed(value.length);

          final bytesDownloaded = offset - initialOffset;
          final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;
          wal.storageOffset = offset;
          wal.syncSpeedKBps = _currentSpeedKBps;

          if (_currentSpeedKBps > 0) {
            final bytesRemaining = wal.storageTotalBytes - offset;
            wal.syncEtaSeconds = (bytesRemaining / 1024 / _currentSpeedKBps).round();
          }

          progress?.onWalSyncedProgress(progressPercent.clamp(0.0, 1.0), speedKBps: _currentSpeedKBps);
          listener.onWalUpdated();

          // Check if transfer is complete
          if (offset >= wal.storageTotalBytes) {
            if (!completer.isCompleted) {
              completer.complete();
            }
          }
        },
        onError: (error) {
          if (!completer.isCompleted) {
            completer.completeError(error);
          }
        },
        onDone: () {
          if (!completer.isCompleted) {
            completer.complete();
          }
        },
      );

      // Wait for transfer to complete with timeout
      try {
        await completer.future.timeout(
          const Duration(minutes: 5),
          onTimeout: () {
            debugPrint("SDCardWalSync WiFi: Transfer timeout");
          },
        );
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Transfer error: $e");
      }

      // Flush all collected data in chunks
      while (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        timerStart += sdcardChunkSizeSecs;
        try {
          var file = await _flushToDisk(wal, chunk, timerStart);
          await _registerSingleChunk(wal, file, timerStart);
        } catch (e) {
          debugPrint('SDCardWalSync WiFi: Error flushing chunk: $e');
        }
      }

      // Flush any remaining frames
      if (bytesLeft < bytesData.length) {
        var chunk = bytesData.sublist(bytesLeft);
        timerStart += sdcardChunkSizeSecs;
        try {
          var file = await _flushToDisk(wal, chunk, timerStart);
          await _registerSingleChunk(wal, file, timerStart);
        } catch (e) {
          debugPrint('SDCardWalSync WiFi: Error flushing final chunk: $e');
        }
      }

      // Cleanup
      await audioSubscription.cancel();
      await wifiStatusSubscription?.cancel();
      await wifiReceiver.stop();

      // Stop WiFi on device (may fail if device already disconnected, that's OK)
      try {
        await connection.stopWifiSync();
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: stopWifiSync failed (device may have disconnected): $e");
      }

      // Clear SD card storage (may fail if device disconnected during WiFi sync)
      // Device disconnecting after WiFi transfer is normal - it switches back to BLE mode
      try {
        if (_device != null) {
          await _writeToStorage(_device!.id, wal.fileNum, 1, 0);
        }
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: Could not clear SD card storage (device may have disconnected): $e");
      }

      wal.status = WalStatus.synced;
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      listener.onWalUpdated();

      _resetSyncState();
      return resp;
    } catch (e) {
      debugPrint("SDCardWalSync WiFi: Error during sync: $e");

      // Ensure cleanup on error
      try {
        await connection.stopWifiSync();
      } catch (_) {}

      await wifiReceiver.stop();

      _resetSyncState();
      rethrow;
    }
  }
}
