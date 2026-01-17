import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/logger.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/transports/tcp_transport.dart';
import 'package:omi/services/devices/wifi_sync_error.dart';
import 'package:omi/services/services.dart';
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
  @override
  bool get isSyncing => _isSyncing;

  int _totalBytesDownloaded = 0;
  DateTime? _downloadStartTime;
  double _currentSpeedKBps = 0.0;
  @override
  double get currentSpeedKBps => _currentSpeedKBps;

  SDCardWalSyncImpl(this.listener);

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
    _wifiSpeedWindowStart = null;
    _wifiSpeedWindowBytes = 0;
    _lastProgressUpdate = null;
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
  static const Duration _speedUpdateInterval = Duration(seconds: 3);
  static const Duration _progressUpdateInterval = Duration(seconds: 1);

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
        _currentSpeedKBps = (_wifiSpeedWindowBytes / 1024) / windowSeconds;
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
      Logger.debug(
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

    Logger.debug("SDCardWalSync _flushToDisk: Wrote ${data.length} bytes to $filePath");

    return file;
  }

  Future _readStorageBytesToFile(Wal wal, Function(File f, int offset, int timerStart) callback) async {
    var deviceId = wal.device;
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;
    int timerStart = wal.timerStart;

    Logger.debug("_readStorageBytesToFile ${offset}");

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

      if (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        timerStart += sdcardChunkSizeSecs;
        try {
          var file = await _flushToDisk(wal, chunk, timerStart);
          await callback(file, offset, timerStart);
        } catch (e) {
          Logger.debug('Error in callback during chunking: $e');
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
        Logger.debug('SD card read timeout: ${error.message}');
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
    Logger.debug("SDCard sync (two-phase): ${wal.id} byte offset: ${wal.storageOffset} ts ${wal.timerStart}");

    if (_localSync == null) {
      Logger.debug("SDCard: ERROR - LocalWalSync not available, aborting to preserve data safety");
      throw Exception('Local sync service not available. Cannot safely download SD card data.');
    }

    int chunksDownloaded = 0;
    int lastOffset = wal.storageOffset;
    int totalBytesToDownload = wal.storageTotalBytes - wal.storageOffset;

    Logger.debug(
        "SDCard Phase 1: Downloading ~${(totalBytesToDownload / 1024).toStringAsFixed(1)} KB to phone storage");

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

        Logger.debug(
            "SDCard: Chunk $chunksDownloaded downloaded (ts: $timerStart, speed: ${_currentSpeedKBps.toStringAsFixed(1)} KB/s)");
      });
    } catch (e) {
      await _storageStream?.cancel();
      Logger.debug('SDCard download failed: $e');
      if (chunksDownloaded > 0) {
        Logger.debug("SDCard: $chunksDownloaded chunks saved before failure");
      }
      rethrow;
    }

    if (chunksDownloaded == 0) {
      Logger.debug("SDCard: No chunks downloaded");
      return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    }

    Logger.debug("SDCard Phase 1 complete: $chunksDownloaded chunks downloaded");

    Logger.debug("SDCard Phase 3: Clearing SD card storage");
    await _writeToStorage(wal.device, wal.fileNum, 1, 0);

    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  Future<void> _registerSingleChunk(Wal wal, File file, int timerStart) async {
    if (_localSync == null) {
      Logger.debug("SDCard: WARNING - Cannot register chunk, LocalWalSync not available");
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
    Logger.debug(
        "SDCard: Registered chunk (ts: $timerStart) with LocalWalSync - codec=${localWal.codec}, sampleRate=${localWal.sampleRate}, channel=${localWal.channel}");
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
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

        resp.newConversationIds
            .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

        wal.status = WalStatus.synced;
      } catch (e) {
        Logger.debug("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
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
    var walToSync = _wals.where((w) => w == wal).toList().first;

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

      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

      wal.status = WalStatus.synced;
    } catch (e) {
      Logger.debug("SDCardWalSync: Error syncing WAL ${wal.id}: $e");
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

  // Legacy methods - kept for interface compatibility but no longer used in AP mode
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
      final setupResult = await connection.setupWifiSync(ssid, password);
      if (!setupResult.success) {
        _resetSyncState();
        final errorMessage = setupResult.errorMessage ?? 'Failed to setup WiFi on device';
        final errorCode = setupResult.errorCode;
        if (errorCode != null) {
          debugPrint(
              "SDCardWalSync WiFi: Setup failed with error code 0x${errorCode.code.toRadixString(16)}: ${errorCode.userMessage}");
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

      debugPrint("SDCardWalSync WiFi: Step 4 - Connecting phone to device WiFi AP");
      final wifiResult = await wifiNetwork.connectToAp(ssid, password: password);
      if (!wifiResult.success) {
        await _cleanupWifiSync(null, wifiNetwork, ssid, connection, deviceId: deviceId);
        final errorMsg = wifiResult.errorMessage ?? wifiResult.error?.userMessage ?? 'Failed to connect to device WiFi';
        connectionListener?.onConnectionFailed(errorMsg);
        throw WifiSyncException('WiFi connection failed: $errorMsg');
      }

      // Step 6: Start TCP server and wait for device to connect
      const tcpPort = 12345;
      debugPrint("SDCardWalSync WiFi: Step 6 - Starting TCP server on port $tcpPort");
      tcpTransport = TcpTransport(deviceId, port: tcpPort, connectionTimeout: const Duration(seconds: 60));
      try {
        await tcpTransport.connect();
        debugPrint("SDCardWalSync WiFi: Device connected to TCP server!");
        // Notify: Connected successfully
        connectionListener?.onConnected();
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: TCP server error: $e");
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

      List<List<int>> bytesData = [];
      var bytesLeft = 0;
      var chunkSize = sdcardChunkSizeSecs * wal.codec.getFramesPerSecond();
      var timerStart = wal.timerStart;

      final initialOffset = wal.storageOffset;
      var offset = wal.storageOffset;
      final totalBytes = wal.storageTotalBytes - initialOffset;

      List<int> tcpBuffer = [];

      // Step 7: Send command to start SD card read over BLE
      debugPrint("SDCardWalSync WiFi: Step 7 - Sending start read command over BLE...");

      final readStarted = await _writeToStorage(deviceId, wal.fileNum, 0, offset);
      if (!readStarted) {
        await _cleanupWifiSync(tcpTransport, wifiNetwork, ssid, connection, deviceId: deviceId);
        throw WifiSyncException('Failed to start storage read');
      }

      // Step 7b: Disconnect BLE intentionally before data transfer
      debugPrint("SDCardWalSync WiFi: Disconnecting BLE before data transfer (expected)...");
      try {
        ServiceManager.instance().device.setWifiSyncInProgress(true);
        await ServiceManager.instance().device.disconnectDevice();
      } catch (e) {
        debugPrint("SDCardWalSync WiFi: BLE disconnect error (non-fatal): $e");
      }
      connection = null;

      // Step 8: Receive and process data over WiFi
      debugPrint("SDCardWalSync WiFi: Step 8 - Receiving data ($totalBytes bytes to download)");

      final completer = Completer<void>();
      StreamSubscription? audioSubscription;

      final audioStream = tcpTransport.dataStream;

      // Track position within 440-byte logical blocks
      int globalBytePosition = 0;

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
            if (posInBlock > 0 && bytesRemainingInBlock < 12) {
              if (packageOffset + bytesRemainingInBlock > bufferLength) {
                break;
              }
              packageOffset += bytesRemainingInBlock;
              bytesProcessed = packageOffset;
              continue;
            }

            // Check if frame would extend beyond block boundary
            if (posInBlock > 0 && packageSize + 1 > bytesRemainingInBlock) {
              if (packageOffset + bytesRemainingInBlock > bufferLength) {
                break;
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
                break;
              }
              continue;
            }

            // Check if we have the complete frame
            if (packageOffset + 1 + packageSize > bufferLength) {
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

          // Remove processed bytes from buffer
          if (bytesProcessed > 0) {
            tcpBuffer = List<int>.from(tcpBuffer.skip(bytesProcessed));
          }

          offset += value.length;
          final (shouldUpdateProgress, shouldUpdateSpeed) = _updateWifiSpeed(value.length);

          wal.storageOffset = offset;

          if (shouldUpdateProgress || shouldUpdateSpeed) {
            final bytesDownloaded = offset - initialOffset;
            final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;

            if (shouldUpdateSpeed && _currentSpeedKBps > 0) {
              wal.syncSpeedKBps = _currentSpeedKBps;
              final bytesRemaining = wal.storageTotalBytes - offset;
              wal.syncEtaSeconds = (bytesRemaining / 1024 / _currentSpeedKBps).round();
            }

            progress?.onWalSyncedProgress(progressPercent.clamp(0.0, 1.0), speedKBps: wal.syncSpeedKBps);
            listener.onWalUpdated();
          }

          // Check if transfer is complete
          if (offset >= wal.storageTotalBytes) {
            // Send final progress update
            _finalizeWifiSpeed();
            final bytesDownloaded = offset - initialOffset;
            final progressPercent = totalBytes > 0 ? bytesDownloaded / totalBytes : 0.0;
            wal.syncSpeedKBps = _currentSpeedKBps;
            wal.syncEtaSeconds = 0;
            progress?.onWalSyncedProgress(progressPercent.clamp(0.0, 1.0), speedKBps: _currentSpeedKBps);
            listener.onWalUpdated();

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
            Logger.debug("SDCardWalSync WiFi: Transfer timeout");
          },
        );
      } catch (e) {
        Logger.debug("SDCardWalSync WiFi: Transfer error: $e");
      }

      // Check if cancelled - still save any data received before cancellation
      final wasCancelled = _isCancelled;

      // Flush all collected data in chunks
      while (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        timerStart += sdcardChunkSizeSecs;
        try {
          var file = await _flushToDisk(wal, chunk, timerStart);
          await _registerSingleChunk(wal, file, timerStart);
        } catch (e) {
          Logger.debug('SDCardWalSync WiFi: Error flushing chunk: $e');
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
          Logger.debug('SDCardWalSync WiFi: Error flushing final chunk: $e');
        }
      }

      // Step 9: Cleanup
      debugPrint("SDCardWalSync WiFi: Step 9 - Cleanup");
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

      // Only clear SD card storage if transfer completed fully (not cancelled)
      if (!wasCancelled) {
        if (bleConnection != null) {
          try {
            await _writeToStorage(deviceId, wal.fileNum, 1, 0);
          } catch (e) {
            debugPrint("SDCardWalSync WiFi: Could not clear SD card storage: $e");
          }
        } else {
          debugPrint("SDCardWalSync WiFi: Skipping SD card clear - no BLE connection");
        }
        wal.status = WalStatus.synced;
      } else {
        // Cancelled - don't clear SD card, WAL remains in 'miss' status
        // but we saved the partial data as local WAL files
        debugPrint("SDCardWalSync WiFi: Cancelled - SD card not cleared, saved partial data");
      }

      if (bleConnection != null) {
        try {
          await bleConnection.stopWifiSync();
        } catch (e) {
          debugPrint("SDCardWalSync WiFi: Error stopping WiFi on device: $e");
        }
      }

      ServiceManager.instance().device.setWifiSyncInProgress(false);

      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      wal.syncMethod = SyncMethod.ble;
      listener.onWalUpdated();
      _resetSyncState();

      if (wasCancelled) {
        debugPrint("SDCardWalSync WiFi: Cancelled - partial data saved, user can retry for remaining");
        return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
      }

      debugPrint("SDCardWalSync WiFi: Sync completed successfully");
      return resp;
    } catch (e) {
      Logger.debug("SDCardWalSync WiFi: Error during sync: $e");

      ServiceManager.instance().device.setWifiSyncInProgress(false);

      // Reset WAL sync state on error
      wal.isSyncing = false;
      wal.syncStartedAt = null;
      wal.syncEtaSeconds = null;
      wal.syncSpeedKBps = null;
      wal.syncMethod = SyncMethod.ble;
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
