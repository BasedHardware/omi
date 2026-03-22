import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Offline storage sync for new multi-file firmware protocol (CMD_LIST_FILES 0x10,
/// CMD_READ_FILE 0x11, CMD_DELETE_FILE 0x12). Downloads individual files from
/// device LittleFS storage to phone, then hands them to LocalWalSync for upload.
class StorageSyncImpl implements StorageSync {
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

  StorageSyncImpl(this.listener);

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
    }
  }

  void _resetSyncState() {
    _isCancelled = false;
    _isSyncing = false;
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
    if (_device == null) return false;
    try {
      var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) return false;
      final status = await connection.getStorageFileStats();
      return status != null && status.fileCount > 0;
    } catch (e) {
      Logger.debug('StorageSync: hasFilesToSync error: $e');
      return false;
    }
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    if (_device == null) return [];

    try {
      var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
      if (connection == null) return [];

      final status = await connection.getStorageFileStats();
      if (status == null || status.fileCount == 0) return [];

      final files = await connection.listStorageFiles();
      if (files.isEmpty) return [];

      BleAudioCodec codec = await connection.getAudioCodec();
      var pd = await _device!.getDeviceInfo(connection);
      String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";

      List<Wal> wals = [];
      for (final file in files) {
        int fps = codec.getFramesPerSecond();
        int frameLen = codec.getFramesLengthInBytes();
        int seconds = fps > 0 && frameLen > 0 ? (file.sizeBytes / frameLen) ~/ fps : 0;
        if (seconds < 1) continue;

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

      _wals = wals;
      Logger.debug('StorageSync: Found ${wals.length} files to sync');
      return wals;
    } catch (e) {
      Logger.debug('StorageSync: Error getting missing wals: $e');
      return [];
    }
  }

  @override
  Future deleteWal(Wal wal) async {
    _wals = _wals.where((w) => w.id != wal.id).toList();
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    _wals = _wals.where((w) => w.status != WalStatus.synced).toList();
  }

  @override
  Future<void> deleteAllPendingWals() async {
    _wals = _wals.where((w) => w.status != WalStatus.miss).toList();
  }

  @override
  void start() {}

  @override
  Future stop() async {
    cancelSync();
    await _storageStream?.cancel();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    if (_device == null) return null;

    final wals = await getMissingWals();
    if (wals.isEmpty) {
      Logger.debug("StorageSync: No files to sync");
      return null;
    }

    _resetSyncState();
    _isSyncing = true;

    DebugLogManager.logInfo('StorageSync: Starting sync of ${wals.length} files');

    try {
      for (int i = 0; i < wals.length; i++) {
        if (_isCancelled) break;

        final wal = wals[i];
        double fileProgress = i / wals.length;
        progress?.onWalSyncedProgress(fileProgress, speedKBps: _currentSpeedKBps);

        Logger.debug(
          'StorageSync: Downloading file ${i + 1}/${wals.length} (index=${wal.fileNum}, size=${wal.storageTotalBytes})',
        );
        await _syncSingleFile(wal);

        listener.onWalUpdated();
      }
    } catch (e) {
      Logger.debug('StorageSync: Error during sync: $e');
      DebugLogManager.logError(e, null, 'StorageSync failed', {'device': _device?.id});
    } finally {
      _isSyncing = false;
    }

    progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    _resetSyncState();
    _isSyncing = true;

    try {
      progress?.onWalSyncedProgress(0.0);
      await _syncSingleFile(wal);
      progress?.onWalSyncedProgress(1.0, speedKBps: _currentSpeedKBps);
      listener.onWalUpdated();
    } catch (e) {
      Logger.debug('StorageSync: Error syncing file: $e');
    } finally {
      _isSyncing = false;
    }

    return SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
  }

  /// Download a single file from device storage to phone local disk,
  /// then register it with LocalWalSync for cloud upload.
  Future<void> _syncSingleFile(Wal wal) async {
    if (_device == null) return;

    var connection = await ServiceManager.instance().device.ensureConnection(_device!.id);
    if (connection == null) throw Exception('Device not connected');

    _downloadStartTime = DateTime.now();
    _totalBytesDownloaded = 0;

    // Set up BLE listener for incoming data
    final completer = Completer<void>();
    List<List<int>> chunks = [];
    int bytesReceived = 0;
    Timer? inactivityTimer;

    void resetInactivityTimer() {
      inactivityTimer?.cancel();
      inactivityTimer = Timer(const Duration(seconds: 10), () {
        if (!completer.isCompleted) {
          Logger.debug('StorageSync: Inactivity timeout for file ${wal.fileNum}');
          completer.complete();
        }
      });
    }

    _storageStream = await connection.getBleStorageBytesListener(
      onStorageBytesReceived: (List<int> value) {
        if (_isCancelled || completer.isCompleted) return;

        // Single-byte responses are control signals
        if (value.length == 1) {
          final code = value[0];
          if (code == 100) {
            // Transfer complete
            Logger.debug('StorageSync: File ${wal.fileNum} transfer complete');
            if (!completer.isCompleted) completer.complete();
            return;
          }
          if (code != 0) {
            Logger.debug('StorageSync: Error code $code for file ${wal.fileNum}');
            if (!completer.isCompleted) completer.completeError(Exception('Storage error: $code'));
            return;
          }
          return;
        }

        // Data packets: [timestamp:4][audio_data:N]
        // Strip the 4-byte timestamp prefix, keep raw audio data
        if (value.length > 4) {
          final audioData = value.sublist(4);
          chunks.add(audioData);
          bytesReceived += audioData.length;
          _updateSpeed(audioData.length);
          resetInactivityTimer();

          // Check if we've received all expected bytes
          if (wal.storageTotalBytes > 0 && bytesReceived >= wal.storageTotalBytes) {
            Logger.debug(
              'StorageSync: File ${wal.fileNum} all bytes received ($bytesReceived/${wal.storageTotalBytes})',
            );
            if (!completer.isCompleted) completer.complete();
          }
        }
      },
    );

    if (_storageStream == null) {
      throw Exception('Failed to set up storage listener');
    }

    resetInactivityTimer();

    // Send CMD_READ_FILE command: [0x11, file_index, offset_bytes]
    await connection.writeToStorage(wal.fileNum, 0x11, 0);

    // Wait for transfer to complete
    try {
      await completer.future.timeout(const Duration(minutes: 5));
    } on TimeoutException {
      Logger.debug('StorageSync: File ${wal.fileNum} transfer timed out');
    }

    inactivityTimer?.cancel();
    await _storageStream?.cancel();
    _storageStream = null;

    if (chunks.isEmpty) {
      Logger.debug('StorageSync: No data received for file ${wal.fileNum}');
      return;
    }

    // Flush to local disk in WAL format: [frame_length_u32][frame_data]...
    final file = await _flushToDisk(wal, chunks, wal.timerStart);

    // Register with LocalWalSync for cloud upload
    await _registerWithLocalSync(wal, file, chunks.length);

    Logger.debug('StorageSync: File ${wal.fileNum} synced ($bytesReceived bytes, ${chunks.length} chunks)');
  }

  /// Write audio chunks to disk in WAL format compatible with /v1/sync-local-files.
  Future<File> _flushToDisk(Wal wal, List<List<int>> chunks, int timerStart) async {
    final directory = await getApplicationDocumentsDirectory();
    String filePath = '${directory.path}/${wal.getFileNameByTimeStarts(timerStart)}';

    List<int> data = [];
    for (final chunk in chunks) {
      // Each frame: [length_u32_le][frame_bytes]
      data.addAll(Uint32List.fromList([chunk.length]).buffer.asUint8List());
      data.addAll(chunk);
    }

    final file = File(filePath);
    await file.writeAsBytes(data);
    Logger.debug('StorageSync: Wrote ${data.length} bytes to $filePath');
    return file;
  }

  /// Register a downloaded file with LocalWalSync so it gets uploaded to backend.
  Future<void> _registerWithLocalSync(Wal wal, File file, int chunkCount) async {
    if (_localSync == null) {
      Logger.debug("StorageSync: WARNING - Cannot register file, LocalWalSync not available");
      return;
    }

    int fps = wal.codec.getFramesPerSecond();
    int chunkSeconds = fps > 0 ? chunkCount ~/ fps : wal.seconds;

    Wal localWal = Wal(
      codec: wal.codec,
      channel: wal.channel,
      sampleRate: wal.sampleRate,
      timerStart: wal.timerStart,
      filePath: file.path.split('/').last,
      storage: WalStorage.disk,
      status: WalStatus.miss,
      device: wal.device,
      deviceModel: wal.deviceModel,
      seconds: chunkSeconds,
      totalFrames: chunkCount,
      syncedFrameOffset: 0,
      originalStorage: WalStorage.sdcard,
    );

    await _localSync!.addExternalWal(localWal);
    Logger.debug('StorageSync: Registered file (ts=${wal.timerStart}) with LocalWalSync');
  }
}
