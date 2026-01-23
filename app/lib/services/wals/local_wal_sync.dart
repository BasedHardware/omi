import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/wal_file_manager.dart';

class LocalWalSyncImpl implements LocalWalSync {
  List<Wal> _wals = const [];

  List<List<int>> _frames = [];
  List<bool> _frameSynced = [];

  Timer? _chunkingTimer;
  Timer? _flushingTimer;

  IWalSyncListener listener;

  int _framesPerSecond = 100;
  BleAudioCodec _codec = BleAudioCodec.opus;
  String? _deviceId;
  String? _deviceModel;

  LocalWalSyncImpl(this.listener);

  @override
  void cancelSync() {
    // Local sync doesn't support cancellation yet
  }

  @override
  Future<void> addExternalWal(Wal wal) async {
    final existingIndex = _wals.indexWhere((w) => w.id == wal.id);
    if (existingIndex >= 0) {
      Logger.debug("LocalWalSync: WAL ${wal.id} already exists, skipping");
      return;
    }
    _wals.add(wal);
    await _saveWalsToFile();
    listener.onWalUpdated();
    Logger.debug("LocalWalSync: Added external WAL ${wal.id} (${wal.seconds}s)");
  }

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
    Logger.debug("wal service start: ${_wals.length}");

    // Run migrations for legacy Limitless files
    final migratedCount = await WalFileManager.migrateLegacyLimitlessFiles(_wals);
    if (migratedCount > 0) {
      // Reload WALs after migration
      _wals = await WalFileManager.loadWals();
      Logger.debug("wal service after migration: ${_wals.length}");
    }

    // Fix any inconsistent WAL states from old implementations
    await WalFileManager.migrateInconsistentWals(_wals);

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

  @override
  Future onAudioCodecChanged(BleAudioCodec codec) async {
    if (codec.getFramesPerSecond() == _framesPerSecond && codec == _codec) {
      return;
    }

    await _chunk();
    await _flush();
    _frames = [];
    _frameSynced = [];

    _framesPerSecond = codec.getFramesPerSecond();
    _codec = codec;
  }

  @override
  void setDeviceInfo(String? deviceId, String? deviceModel) {
    _deviceId = deviceId;
    _deviceModel = deviceModel;
  }

  Future _chunk() async {
    if (_frames.isEmpty) {
      Logger.debug("Frames are empty");
      return;
    }

    var lossesThreshold = 10 * _framesPerSecond;
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
      int syncedOffset = 0;
      for (var i = low; i < high; i++) {
        if (_frameSynced[i]) {
          syncedOffset++;
        } else {
          break;
        }
      }
      Logger.debug("${low} - ${high} - ${syncedOffset} - ${chunkFrameCount} - ${_framesPerSecond}");

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

    Logger.debug("_chunk wals ${_wals.length}");

    _frames.removeRange(0, pivot);
    _frameSynced.removeRange(0, pivot);
  }

  Future _flush() async {
    Logger.debug("_flushing");
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

          final byteFrame = ByteData(frame.length);
          for (int i = 0; i < frame.length; i++) {
            byteFrame.setUint8(i, frame[i]);
          }
          data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
          data.addAll(byteFrame.buffer.asUint8List());
        }
        final file = File(filePath);
        await file.writeAsBytes(data);
        wal.filePath = wal.getFileName();
        wal.storage = WalStorage.disk;

        Logger.debug("_flush file ${wal.filePath}");

        _wals[i] = wal;
      }
    }

    await _saveWalsToFile();
  }

  Future<void> _saveWalsToFile() async {
    Logger.debug('Saving WALs to file');
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
        Logger.debug(e.toString());
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

  @override
  Future<List<Wal>> getAllWals() async {
    return List.from(_wals);
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  @override
  void onByteStream(List<int> value) async {
    _frames.add(value);
    _frameSynced.add(false);
  }

  @override
  void onBytesSync(List<int> value) {
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
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    await _flush();

    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.disk).toList();
    if (wals.isEmpty) {
      Logger.debug("All synced!");
      return null;
    }

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
        Logger.debug("sync id ${wal.id} ${wal.timerStart}");
        if (wal.filePath == null) {
          Logger.debug("file path is not found. wal id ${wal.id}");
          wal.status = WalStatus.corrupted;
          continue;
        }

        final fullPath = await Wal.getFilePath(wal.filePath);
        Logger.debug("sync wal: ${wal.id} file: $fullPath");

        try {
          if (fullPath == null) {
            Logger.debug("could not construct file path for wal id ${wal.id}");
            wal.status = WalStatus.corrupted;
            continue;
          }

          File file = File(fullPath);
          if (!file.existsSync()) {
            Logger.debug("file $fullPath does not exist");
            wal.status = WalStatus.corrupted;
            continue;
          }
          files.add(file);
          wal.isSyncing = true;
        } catch (e) {
          wal.status = WalStatus.corrupted;
          Logger.debug(e.toString());
        }
      }

      if (files.isEmpty) {
        Logger.debug("Files are empty");
        continue;
      }

      progress?.onWalSyncedProgress((left).toDouble() / wals.length);

      listener.onWalUpdated();
      try {
        var partialRes = await syncLocalFiles(files);

        resp.newConversationIds
            .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
        resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
            .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

        for (var j = left; j <= right; j++) {
          if (j < wals.length) {
            var wal = wals[j];
            wals[j].status = WalStatus.synced;
            wals[j].isSyncing = false;
            wals[j].syncStartedAt = null;
            wals[j].syncEtaSeconds = null;

            listener.onWalSynced(wal);
          }
        }
      } catch (e) {
        Logger.debug('Local WAL sync failed: $e');
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

    progress?.onWalSyncedProgress(1.0);
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
    IWifiConnectionListener? connectionListener,
  }) async {
    await _flush();

    var walToSync = _wals.where((w) => w == wal).toList().first;

    var resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    late File walFile;
    if (wal.filePath == null) {
      Logger.debug("file path is not found. wal id ${wal.id}");
      wal.status = WalStatus.corrupted;
    }
    try {
      final fullPath = await Wal.getFilePath(wal.filePath);
      if (fullPath == null) {
        Logger.debug("could not construct file path for wal id ${wal.id}");
        wal.status = WalStatus.corrupted;
      } else {
        File file = File(fullPath);
        if (!file.existsSync()) {
          Logger.debug("file $fullPath does not exist");
          wal.status = WalStatus.corrupted;
        } else {
          walFile = file;
          wal.isSyncing = true;
        }
      }
    } catch (e) {
      wal.status = WalStatus.corrupted;
      Logger.debug(e.toString());
    }

    listener.onWalUpdated();
    try {
      var partialRes = await syncLocalFiles([walFile]);

      resp.newConversationIds
          .addAll(partialRes.newConversationIds.where((id) => !resp.newConversationIds.contains(id)));
      resp.updatedConversationIds.addAll(partialRes.updatedConversationIds
          .where((id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id)));

      walToSync.status = WalStatus.synced;
      walToSync.isSyncing = false;
      walToSync.syncStartedAt = null;
      walToSync.syncEtaSeconds = null;

      listener.onWalSynced(wal);
    } catch (e) {
      Logger.debug('Single WAL sync failed: $e');
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
