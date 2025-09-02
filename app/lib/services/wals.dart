import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:path_provider/path_provider.dart';

const chunkSizeInSeconds = 60;
const flushIntervalInSeconds = 90;
const sdcardChunkSizeSecs = 60;
const newFrameSyncDelaySeconds = 15;

abstract class IWalSyncProgressListener {
  void onWalSyncedProgress(double percentage); // 0..1
}

abstract class IWalServiceListener extends IWalSyncListener {
  void onStatusChanged(WalServiceStatus status);
}

abstract class IWalSyncListener {
  void onWalUpdated();
  void onWalSynced(Wal wal, {ServerConversation? conversation});
}

abstract class IWalSync {
  Future<List<Wal>> getMissingWals();
  Future deleteWal(Wal wal);
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress});
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress});

  void start();
  Future stop();
}

abstract class IWalService {
  void start();
  Future stop();

  void subscribe(IWalServiceListener subscription, Object context);
  void unsubscribe(Object context);

  WalSyncs getSyncs();
}

enum WalServiceStatus {
  init,
  ready,
  stop,
}

enum WalStatus {
  inProgress,
  miss,
  synced,
  corrupted,
}

enum WalStorage {
  mem,
  disk,
  sdcard,
}

class WalStats {
  final int totalFiles;
  final int phoneFiles;
  final int sdcardFiles;
  final int phoneSize; // in bytes
  final int sdcardSize; // in bytes
  final int syncedFiles;
  final int missedFiles;

  WalStats({
    required this.totalFiles,
    required this.phoneFiles,
    required this.sdcardFiles,
    required this.phoneSize,
    required this.sdcardSize,
    required this.syncedFiles,
    required this.missedFiles,
  });

  String get totalSizeFormatted => _formatBytes(phoneSize + sdcardSize);
  String get phoneSizeFormatted => _formatBytes(phoneSize);
  String get sdcardSizeFormatted => _formatBytes(sdcardSize);

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}

class Wal {
  int timerStart; // in seconds
  BleAudioCodec codec;
  int channel;
  int sampleRate;
  int seconds;
  String device;
  String? deviceModel;

  WalStatus status;
  WalStorage storage;

  String? filePath;
  List<List<int>> data = [];
  int storageOffset = 0;
  int storageTotalBytes = 0;
  int fileNum = 1;

  bool isSyncing = false;
  DateTime? syncStartedAt;
  int? syncEtaSeconds;

  int frameSize = 160;

  int totalFrames = 0; // Total frames in this WAL
  int syncedFrameOffset = 0; // How many frames from start are synced (continuous)

  String get id => '${device}_$timerStart';

  Wal(
      {required this.timerStart,
      required this.codec,
      required this.seconds,
      this.sampleRate = 16000,
      this.channel = 1,
      this.status = WalStatus.inProgress,
      this.storage = WalStorage.mem,
      this.filePath,
      this.device = "phone",
      this.deviceModel,
      this.storageOffset = 0,
      this.storageTotalBytes = 0,
      this.fileNum = 1,
      this.data = const [],
      this.totalFrames = 0,
      this.syncedFrameOffset = 0}) {
    frameSize = codec.getFrameSize();
  }

  factory Wal.fromJson(Map<String, dynamic> json) {
    return Wal(
      timerStart: json['timer_start'],
      codec: mapNameToCodec(json['codec']),
      channel: json['channel'] ?? 1,
      sampleRate: json['sample_rate'] ?? 16000,
      status: WalStatus.values.asNameMap()[json['status']] ?? WalStatus.inProgress,
      storage: WalStorage.values.asNameMap()[json['storage']] ?? WalStorage.mem,
      filePath: json['file_path'],
      seconds: json['seconds'] ?? chunkSizeInSeconds,
      device: json['device'] ?? "phone",
      deviceModel: json['device_model'],
      storageOffset: json['storage_offset'] ?? 0,
      storageTotalBytes: json['storage_total_bytes'] ?? 0,
      fileNum: json['file_num'] ?? 1,
      totalFrames: json['total_frames'] ?? 0,
      syncedFrameOffset: json['synced_frame_offset'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timer_start': timerStart,
      'codec': codec.toString(),
      'channel': channel,
      'sample_rate': sampleRate,
      'status': status.name,
      'storage': storage.name,
      'file_path': filePath,
      'seconds': seconds,
      'device': device,
      'device_model': deviceModel,
      'storage_offset': storageOffset,
      'storage_total_bytes': storageTotalBytes,
      'file_num': fileNum,
      'total_frames': totalFrames,
      'synced_frame_offset': syncedFrameOffset,
    };
  }

  static List<Wal> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => Wal.fromJson(e)).toList();

  getFileName() {
    return "audio_${device.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase()}_${codec}_${sampleRate}_${channel}_fs${frameSize}_${timerStart}.bin";
  }

  /// Get the full file path, handling both old full paths and new filename-only storage
  static Future<String?> getFilePath(String? pathOrName) async {
    if (pathOrName == null || pathOrName.isEmpty) {
      return null;
    }

    final directory = await getApplicationDocumentsDirectory();
    if (pathOrName.contains('/')) {
      final filename = pathOrName.split('/').last;
      return '${directory.path}/$filename';
    }
    return '${directory.path}/$pathOrName';
  }
}

class SDCardWalSync implements IWalSync {
  List<Wal> _wals = const [];
  BtDevice? _device;

  StreamSubscription? _storageStream;

  IWalSyncListener listener;

  SDCardWalSync(this.listener);

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
      // bad state?
      debugPrint("SDCard bad state, offset > total");
      storageOffset = 0;
    }

    //> 10s
    BleAudioCodec codec = await _getAudioCodec(deviceId);
    if (totalBytes - storageOffset > 10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
      var seconds = ((totalBytes - storageOffset) / codec.getFramesLengthInBytes()) ~/ codec.getFramesPerSecond();
      var timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - seconds;

      // Device model
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
        syncedFrameOffset: 0, // SD card WALs start unsynced
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

  Future<File> _flushToDisk(List<List<int>> chunk, int timerStart) async {
    final directory = await getApplicationDocumentsDirectory();
    String filePath = '${directory.path}/audio_${timerStart}.bin';
    List<int> data = [];
    for (int i = 0; i < chunk.length; i++) {
      var frame = chunk[i];

      // Format: <length>|<data> ; bytes: 4 | n
      final byteFrame = ByteData(frame.length);
      for (int i = 0; i < frame.length; i++) {
        byteFrame.setUint8(i, frame[i]);
      }
      data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());
    }
    final file = File(filePath);
    await file.writeAsBytes(data);

    return file;
  }

  Future _readStorageBytesToFile(Wal wal, Function(File f, int offset) callback) async {
    var deviceId = wal.device;

    // Move the offset
    int fileNum = wal.fileNum;
    int offset = wal.storageOffset;
    int timerStart = wal.timerStart;
    await _writeToStorage(deviceId, fileNum, 0, offset);

    debugPrint("_readStorageBytesToFile ${offset}");

    // Read
    List<List<int>> bytesData = [];
    var bytesLeft = 0;
    var chunkSize = sdcardChunkSizeSecs * 100;
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    bool hasError = false;

    _storageStream = await _getBleStorageBytesListener(deviceId, onStorageBytesReceived: (List<int> value) async {
      if (value.isEmpty || hasError) return;

      // Process command
      if (value.length == 1) {
        // result codes i guess
        debugPrint('returned $value');
        if (value[0] == 0) {
          // valid command
          debugPrint('good to go');
        } else if (value[0] == 3) {
          debugPrint('bad file size. finishing...');
        } else if (value[0] == 4) {
          // file size is zero.
          debugPrint('file size is zero. going to next one....');
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        } else if (value[0] == 100) {
          // valid end command
          debugPrint('end');
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        } else {
          // bad bit
          debugPrint('Error bit returned');
          if (!completer.isCompleted) {
            completer.complete(true);
          }
        }
        return;
      }

      // Process byte data
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

      // Chunking
      if (bytesData.length - bytesLeft >= chunkSize) {
        var chunk = bytesData.sublist(bytesLeft, bytesLeft + chunkSize);
        bytesLeft += chunkSize;
        timerStart += sdcardChunkSizeSecs;
        try {
          var file = await _flushToDisk(chunk, timerStart);
          await callback(file, offset);
        } catch (e) {
          debugPrint('Error in callback during chunking: $e');
          hasError = true;
          if (!completer.isCompleted) {
            completer.completeError(e);
          }
        }
      }
    });

    try {
      await completer.future;
    } catch (e) {
      await _storageStream?.cancel();
      rethrow;
    }

    // Flush remaining bytes only if no error occurred
    if (!hasError && bytesLeft < bytesData.length - 1) {
      var chunk = bytesData.sublist(bytesLeft);
      timerStart += sdcardChunkSizeSecs;
      var file = await _flushToDisk(chunk, timerStart);
      await callback(file, offset);
    }

    return;
  }

  Future<SyncLocalFilesResponse> _syncWal(final Wal wal, Function(int offset)? updates) async {
    debugPrint("sync wal: ${wal.id} byte offset: ${wal.storageOffset} ts ${wal.timerStart}");

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    List<File> files = [];
    bool syncFailed = false;

    var limit = 2;

    // Read with file chunking
    int lastOffset = 0;
    try {
      await _readStorageBytesToFile(wal, (File file, int offset) async {
        if (syncFailed) return; // Stop processing if sync already failed

        files.add(file);
        lastOffset = offset;

        // Sync files with batch
        if (files.isNotEmpty && files.length % limit == 0) {
          var syncFiles = files.sublist(0, limit);
          files = files.sublist(limit);
          try {
            var partialRes = await syncLocalFiles(syncFiles);
            resp.newConversationIds
                .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
            resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
                .where((id) => !resp.updatedConversationIds.contains(id) && !resp.updatedConversationIds.contains(id)));
          } catch (e) {
            debugPrint('SDCard sync batch failed: $e');
            syncFailed = true;

            var prevOffset = wal.storageOffset;
            await _writeToStorage(wal.device, wal.fileNum, 0, prevOffset);

            await _storageStream?.cancel();
            throw Exception('SDCard sync batch failed: $e');
          }

          // Write offset only if sync succeeded
          if (!syncFailed) {
            await _writeToStorage(wal.device, wal.fileNum, 0, offset);

            // Callback
            if (updates != null) {
              updates(offset);
            }
          }
        }
      });
    } catch (e) {
      syncFailed = true;
      await _storageStream?.cancel();
      rethrow;
    }

    // Stop here if sync failed during chunking
    if (syncFailed) {
      throw Exception('SDCard sync failed during processing');
    }

    // Sync remaining files
    if (files.isNotEmpty) {
      var syncFiles = files;
      try {
        var partialRes = await syncLocalFiles(syncFiles);
        resp.newConversationIds
            .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.updatedConversationIds.contains(id)));
      } catch (e) {
        debugPrint('SDCard sync remaining files failed: $e');
        // Cancel the storage stream to stop further processing
        await _storageStream?.cancel();
        throw Exception('SDCard sync remaining files failed: $e');
      }

      // Write offset
      wal.storageOffset = lastOffset;
      await _writeToStorage(wal.device, wal.fileNum, 0, lastOffset);

      // Callback
      if (updates != null) {
        updates(lastOffset);
      }
    }

    // Clear file only if everything succeeded
    await _writeToStorage(wal.device, wal.fileNum, 1, 0);

    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) {
      debugPrint("All synced!");
      return null;
    }
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    for (var i = wals.length - 1; i >= 0; i--) {
      var wal = wals[i];

      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
      listener.onWalUpdated();

      final storageOffsetStarts = wal.storageOffset;

      var partialRes = await _syncWal(wal, (offset) {
        wal.storageOffset = offset;
        wal.syncEtaSeconds = DateTime.now().difference(wal.syncStartedAt!).inSeconds *
            (wal.storageTotalBytes - wal.storageOffset) ~/
            (wal.storageOffset - storageOffsetStarts);
        listener.onWalUpdated();
      });
      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

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
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);
    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    listener.onWalUpdated();

    final storageOffsetStarts = wal.storageOffset;

    var partialRes = await _syncWal(wal, (offset) {
      walToSync.storageOffset = offset;
      walToSync.syncEtaSeconds = DateTime.now().difference(walToSync.syncStartedAt!).inSeconds *
          (walToSync.storageTotalBytes - wal.storageOffset) ~/
          (walToSync.storageOffset - storageOffsetStarts);
      listener.onWalUpdated();
    });
    resp.newConversationIds.addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
    resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
        .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

    wal.status = WalStatus.synced;
    wal.isSyncing = false;
    wal.syncStartedAt = null;
    wal.syncEtaSeconds = null;

    listener.onWalUpdated();
    return resp;
  }

  void setDevice(BtDevice? device) async {
    _device = device;
    _wals = await _getMissingWals();
    listener.onWalUpdated();
  }

  Future<void> deleteAllSyncedWals() async {
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      await deleteWal(wal);
    }
  }
}

class LocalWalSync implements IWalSync {
  List<Wal> _wals = const [];

  List<List<int>> _frames = [];
  List<bool> _frameSynced = []; // Boolean array matching _frames size

  Timer? _chunkingTimer;
  Timer? _flushingTimer;

  IWalSyncListener listener;

  int _framesPerSecond = 100;
  BleAudioCodec _codec = BleAudioCodec.opus;
  String? _deviceId;
  String? _deviceModel;

  LocalWalSync(this.listener);

  @override
  void start() {
    _initializeWals();
    _chunkingTimer = Timer.periodic(const Duration(seconds: chunkSizeInSeconds + newFrameSyncDelaySeconds), (t) async {
      await _chunk();
    });
    _flushingTimer =
        Timer.periodic(const Duration(seconds: flushIntervalInSeconds + newFrameSyncDelaySeconds), (t) async {
      await _flush();
    });
  }

  Future<void> _initializeWals() async {
    await WalFileManager.init();
    _wals = await WalFileManager.loadWals();
    debugPrint("wal service start: ${_wals.length}");
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

  Future onAudioCodecChanged(BleAudioCodec codec) async {
    if (codec.getFramesPerSecond() == _framesPerSecond && codec == _codec) {
      return;
    }

    // clean
    await _chunk();
    await _flush();
    _frames = [];
    _frameSynced = [];

    // update fps
    _framesPerSecond = codec.getFramesPerSecond();
    _codec = codec;
  }

  void setDeviceInfo(String? deviceId, String? deviceModel) {
    _deviceId = deviceId;
    _deviceModel = deviceModel;
  }

  Future _chunk() async {
    if (_frames.isEmpty) {
      debugPrint("Frames are empty");
      return;
    }

    var lossesThreshold = 10 * _framesPerSecond; // 10s
    var timerEnd = DateTime.now().millisecondsSinceEpoch ~/ 1000 - newFrameSyncDelaySeconds;
    var pivot = _frames.length - newFrameSyncDelaySeconds * _framesPerSecond;
    if (pivot <= 0) {
      return;
    }

    var high = pivot;
    var low = 0;
    var chunk = _frames.sublist(low, high);
    var timerStart = timerEnd - (high - low) ~/ _framesPerSecond;
    var chunkFrameCount = high - low;

    bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      // Checking losses threshold
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
      // track the synced offset
      int syncedOffset = 0;
      for (var i = low; i < high; i++) {
        if (_frameSynced[i]) {
          syncedOffset++;
        } else {
          break;
        }
      }
      debugPrint("${low} - ${high} - ${syncedOffset} - ${chunkFrameCount} - ${_framesPerSecond}");

      Wal wal;
      var walIdx =
          _wals.indexWhere((w) => w.timerStart == timerStart && w.device == (_deviceId ?? "omi") && w.codec == _codec);
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

    debugPrint("_chunk wals ${_wals.length}");

    // clean
    _frames.removeRange(0, pivot);
    _frameSynced.removeRange(0, pivot);
  }

  Future _flush() async {
    debugPrint("_flushing");
    for (var i = 0; i < _wals.length; i++) {
      final wal = _wals[i];

      if (wal.storage == WalStorage.mem) {
        String? filePath = await Wal.getFilePath(wal.getFileName());
        if (filePath == null) {
          throw Exception('Flushing to storage failed. Cannot get file path.');
        }

        List<int> data = [];
        for (int i = 0; i < wal.data.length; i++) {
          var frame = wal.data[i].sublist(3);

          // Format: <length>|<data> ; bytes: 4 | n
          final byteFrame = ByteData(frame.length);
          for (int i = 0; i < frame.length; i++) {
            byteFrame.setUint8(i, frame[i]);
          }
          data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
          data.addAll(byteFrame.buffer.asUint8List());
        }
        final file = File(filePath);
        await file.writeAsBytes(data);
        wal.filePath = wal.getFileName(); // Store only filename, not full path
        wal.storage = WalStorage.disk;

        debugPrint("_flush file ${wal.filePath}");

        _wals[i] = wal;
      }
    }

    await _saveWalsToFile();
  }

  Future<void> _saveWalsToFile() async {
    debugPrint('Saving WALs to file');
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
        debugPrint(e.toString());
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

  Future<List<Wal>> getAllWals() async {
    return List.from(_wals);
  }

  Future<void> deleteAllSyncedWals() async {
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  void onByteStream(List<int> value) async {
    _frames.add(value);
    _frameSynced.add(false); // Initially not synced
  }

  void onBytesSync(List<int> value) {
    // Find the frame index that matches this value by comparing the first 3 bytes
    for (int i = _frames.length - 1; i >= 0; i--) {
      if (_frames[i].length >= 3 &&
          _frames[i][0] == value[0] &&
          _frames[i][1] == value[1] &&
          _frames[i][2] == value[2]) {
        _frameSynced[i] = true;
        break;
      }
    }
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    await _flush();

    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.disk).toList();
    if (wals.isEmpty) {
      debugPrint("All synced!");
      return null;
    }

    // Empty resp
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    var steps = 3;
    for (var i = wals.length - 1; i >= 0; i -= steps) {
      var right = i;
      var left = right - steps;
      if (left < 0) {
        left = 0;
      }

      List<File> files = [];
      for (var j = left; j <= right; j++) {
        var wal = wals[j];
        debugPrint("sync id ${wal.id} ${wal.timerStart}");
        if (wal.filePath == null) {
          debugPrint("file path is not found. wal id ${wal.id}");
          wal.status = WalStatus.corrupted;
          continue;
        }

        final fullPath = await Wal.getFilePath(wal.filePath);
        debugPrint("sync wal: ${wal.id} file: $fullPath");

        try {
          if (fullPath == null) {
            debugPrint("could not construct file path for wal id ${wal.id}");
            wal.status = WalStatus.corrupted;
            continue;
          }

          File file = File(fullPath);
          if (!file.existsSync()) {
            debugPrint("file $fullPath does not exist");
            wal.status = WalStatus.corrupted;
            continue;
          }
          files.add(file);
          wal.isSyncing = true;
        } catch (e) {
          wal.status = WalStatus.corrupted;
          debugPrint(e.toString());
        }
      }

      if (files.isEmpty) {
        debugPrint("Files are empty");
        continue;
      }

      // Progress
      progress?.onWalSyncedProgress((left).toDouble() / wals.length);

      // Sync
      listener.onWalUpdated();
      try {
        var partialRes = await syncLocalFiles(files);

        // Ensure unique
        resp.newConversationIds
            .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

        // Success - update status to synced
        for (var j = left; j <= right; j++) {
          if (j < wals.length) {
            var wal = wals[j];
            wals[j].status = WalStatus.synced; // ref to _wals[]
            wals[j].isSyncing = false;
            wals[j].syncStartedAt = null;
            wals[j].syncEtaSeconds = null;

            // Send
            listener.onWalSynced(wal);
          }
        }
      } catch (e) {
        debugPrint('Local WAL sync failed: $e');
        // Reset syncing state for failed WALs
        for (var j = left; j <= right; j++) {
          if (j < wals.length) {
            wals[j].isSyncing = false;
            wals[j].syncStartedAt = null;
            wals[j].syncEtaSeconds = null;
          }
        }
        rethrow;
      }

      await _saveWalsToFile();
      listener.onWalUpdated();
    }

    // Progress
    progress?.onWalSyncedProgress(1.0);
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    await _flush();

    var walToSync = _wals.where((w) => w == wal).toList().first;

    // Empty resp
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    late File walFile;
    if (wal.filePath == null) {
      debugPrint("file path is not found. wal id ${wal.id}");
      wal.status = WalStatus.corrupted;
    }
    try {
      final fullPath = await Wal.getFilePath(wal.filePath);
      if (fullPath == null) {
        debugPrint("could not construct file path for wal id ${wal.id}");
        wal.status = WalStatus.corrupted;
      } else {
        File file = File(fullPath);
        if (!file.existsSync()) {
          debugPrint("file $fullPath does not exist");
          wal.status = WalStatus.corrupted;
        } else {
          walFile = file;
          wal.isSyncing = true;
        }
      }
    } catch (e) {
      wal.status = WalStatus.corrupted;
      debugPrint(e.toString());
    }

    // Sync
    listener.onWalUpdated();
    try {
      var partialRes = await syncLocalFiles([walFile]);

      // Ensure unique
      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

      // Success - update status to synced
      walToSync.status = WalStatus.synced; // ref to _wals[]
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;

      // Send
      listener.onWalSynced(wal);
    } catch (e) {
      debugPrint('Single WAL sync failed: $e');
      // Reset syncing state for failed WAL
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

class WalSyncs implements IWalSync {
  late LocalWalSync _phoneSync;
  LocalWalSync get phone => _phoneSync;

  late SDCardWalSync _sdcardSync;
  SDCardWalSync get sdcard => _sdcardSync;

  IWalSyncListener listener;

  WalSyncs(this.listener) {
    _phoneSync = LocalWalSync(listener);
    _sdcardSync = SDCardWalSync(listener);
  }

  @override
  Future deleteWal(Wal wal) async {
    await _phoneSync.deleteWal(wal);
    await _sdcardSync.deleteWal(wal);
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    List<Wal> wals = [];
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getMissingWals());
    return wals;
  }

  Future<List<Wal>> getAllWals() async {
    List<Wal> wals = [];
    wals.addAll(await _sdcardSync.getMissingWals());
    wals.addAll(await _phoneSync.getAllWals());
    return wals;
  }

  Future<WalStats> getWalStats() async {
    final allWals = await getAllWals();
    int phoneFiles = 0;
    int sdcardFiles = 0;
    int phoneSize = 0;
    int sdcardSize = 0;
    int syncedFiles = 0;
    int missedFiles = 0;

    for (final wal in allWals) {
      if (wal.storage == WalStorage.sdcard) {
        sdcardFiles++;
        sdcardSize += _estimateWalSize(wal);
      } else {
        phoneFiles++;
        phoneSize += _estimateWalSize(wal);
      }

      if (wal.status == WalStatus.synced) {
        syncedFiles++;
      } else if (wal.status == WalStatus.miss) {
        missedFiles++;
      }
    }

    return WalStats(
      totalFiles: allWals.length,
      phoneFiles: phoneFiles,
      sdcardFiles: sdcardFiles,
      phoneSize: phoneSize,
      sdcardSize: sdcardSize,
      syncedFiles: syncedFiles,
      missedFiles: missedFiles,
    );
  }

  int _estimateWalSize(Wal wal) {
    // Estimate size based on codec, sample rate, channels, and duration
    int bytesPerSecond;
    switch (wal.codec) {
      case BleAudioCodec.opusFS320:
        bytesPerSecond = 16000;
      case BleAudioCodec.opus:
        bytesPerSecond = 8000;
        break;
      case BleAudioCodec.pcm16:
        bytesPerSecond = wal.sampleRate * 2 * wal.channel; // 16-bit samples
        break;
      case BleAudioCodec.pcm8:
        bytesPerSecond = wal.sampleRate * 1 * wal.channel; // 8-bit samples
        break;
      default:
        bytesPerSecond = 8000;
    }
    return bytesPerSecond * wal.seconds;
  }

  Future<void> deleteAllSyncedWals() async {
    await _phoneSync.deleteAllSyncedWals();
    await _sdcardSync.deleteAllSyncedWals();
  }

  @override
  void start() {
    _phoneSync.start();
    _sdcardSync.start();
  }

  @override
  Future stop() async {
    await _phoneSync.stop();
    await _sdcardSync.stop();
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    // sdcard
    var partialRes = await _sdcardSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));
    }

    // phone
    partialRes = await _phoneSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));
    }

    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) {
    if (wal.storage == WalStorage.sdcard) {
      return _sdcardSync.syncWal(wal: wal, progress: progress);
    } else {
      return _phoneSync.syncWal(wal: wal, progress: progress);
    }
  }
}

class WalService implements IWalService, IWalSyncListener {
  final Map<Object, IWalServiceListener> _subscriptions = {};
  WalServiceStatus _status = WalServiceStatus.init;
  WalServiceStatus get status => _status;

  late WalSyncs _syncs;
  WalSyncs get syncs => _syncs;

  WalService() {
    _syncs = WalSyncs(this);
  }

  @override
  void subscribe(IWalServiceListener subscription, Object context) {
    _subscriptions.remove(context.hashCode);
    _subscriptions.putIfAbsent(context.hashCode, () => subscription);

    // retains
    subscription.onStatusChanged(_status);
  }

  @override
  void unsubscribe(Object context) {
    _subscriptions.remove(context.hashCode);
  }

  @override
  void start() {
    _syncs.start();
    _status = WalServiceStatus.ready;
  }

  @override
  Future stop() async {
    await _syncs.stop();

    _status = WalServiceStatus.stop;
    _onStatusChanged(_status);
    _subscriptions.clear();
  }

  void _onStatusChanged(WalServiceStatus status) {
    for (var s in _subscriptions.values) {
      s.onStatusChanged(status);
    }
  }

  @override
  WalSyncs getSyncs() {
    return _syncs;
  }

  @override
  void onWalUpdated() {
    for (var s in _subscriptions.values) {
      s.onWalUpdated();
    }
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {
    for (var s in _subscriptions.values) {
      s.onWalSynced(wal, conversation: conversation);
    }
  }
}
