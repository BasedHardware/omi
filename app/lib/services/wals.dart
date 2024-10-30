import 'dart:async';
import 'dart:collection';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/services/services.dart';
import 'package:path_provider/path_provider.dart';

const chunkSizeInSeconds = 60;
const flushIntervalInSeconds = 90;

abstract class IWalSyncProgressListener {
  void onWalSyncedProgress(double percentage); // 0..1
}

abstract class IWalServiceListener extends IWalSyncListener {
  void onStatusChanged(WalServiceStatus status);
}

abstract class IWalSyncListener {
  void onMissingWalUpdated();
  void onWalSynced(Wal wal, {ServerMemory? memory});
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

class Wal {
  int timerStart; // in seconds
  String codec;
  int channel;
  int sampleRate;
  int seconds;
  String device;

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

  String get id => '${device}_$timerStart';

  Wal(
      {required this.timerStart,
      this.codec = "opus",
      this.sampleRate = 16000,
      this.channel = 1,
      this.status = WalStatus.inProgress,
      this.storage = WalStorage.mem,
      this.filePath,
      this.seconds = chunkSizeInSeconds,
      this.device = "phone",
      this.storageOffset = 0,
      this.storageTotalBytes = 0,
      this.fileNum = 1,
      this.data = const []});

  factory Wal.fromJson(Map<String, dynamic> json) {
    return Wal(
      timerStart: json['timer_start'],
      codec: json['codec'],
      channel: json['channel'],
      sampleRate: json['sample_rate'],
      status: WalStatus.values.asNameMap()[json['status']] ?? WalStatus.inProgress,
      storage: WalStorage.values.asNameMap()[json['storage']] ?? WalStorage.mem,
      filePath: json['file_path'],
      seconds: json['seconds'] ?? chunkSizeInSeconds,
      device: json['device'] ?? "phone",
      storageOffset: json['storage_offset'] ?? 0,
      storageTotalBytes: json['storage_total_bytes'] ?? 0,
      fileNum: json['file_num'] ?? 1,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timer_start': timerStart,
      'codec': codec,
      'channel': channel,
      'sample_rate': sampleRate,
      'status': status.name,
      'storage': storage.name,
      'file_path': filePath,
      'seconds': seconds,
      'device': device,
      'storage_offset': storageOffset,
      'storage_total_bytes': storageTotalBytes,
      'file_num': fileNum,
    };
  }

  static List<Wal> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => Wal.fromJson(e)).toList();

  getFileName() {
    return "audio_${device.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase()}_${codec}_${sampleRate}_${channel}_${timerStart}.bin";
  }
}

class SDCardWalSync implements IWalSync {
  List<Wal> _wals = const [];
  BtDevice? _device;

  StreamSubscription? _storageStream;

  IWalSyncListener listener;

  SDCardWalSync(this.listener);

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

    listener.onMissingWalUpdated();
  }

  Future<List<Wal>> _getMissingWals() async {
    if (_device == null) {
      return [];
    }
    List<Wal> wals = [];
    var storageFiles = await _getStorageList(_device!.id);
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
    if (totalBytes - storageOffset > 10 * 80 * 100) {
      var seconds = ((totalBytes - storageOffset) / 80) ~/ 100; // 80: frame length, 100: frame per seconds
      var timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000 - seconds;
      wals.add(Wal(
        timerStart: timerStart,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        seconds: seconds,
        storageOffset: storageOffset,
        storageTotalBytes: totalBytes,
        fileNum: 1,
        device: _device!.id,
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
    listener.onMissingWalUpdated();
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
    var chunkSizeSecs = 10;
    var chunkSize = chunkSizeSecs * 100;
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    _storageStream = await _getBleStorageBytesListener(deviceId, onStorageBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;

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
        timerStart += chunkSizeSecs;
        var file = await _flushToDisk(chunk, timerStart);
        await callback(file, offset);
      }
    });
    await completer.future;

    // Flush remaining bytes
    if (bytesLeft < bytesData.length - 1) {
      var chunk = bytesData.sublist(bytesLeft);
      timerStart += chunkSizeSecs;
      var file = await _flushToDisk(chunk, timerStart);
      await callback(file, offset);
    }

    return;
  }

  Future<SyncLocalFilesResponse> _syncWal(final Wal wal, Function(int offset)? updates) async {
    debugPrint("sync wal: ${wal.id} byte offset: ${wal.storageOffset} ts ${wal.timerStart}");

    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);
    List<File> files = [];

    var limit = 2;

    // Read with file chunking
    int lastOffset = 0;
    await _readStorageBytesToFile(wal, (File file, int offset) async {
      files.add(file);
      lastOffset = offset;

      // Sync files with batch
      if (files.isNotEmpty && files.length % limit == 0) {
        var syncFiles = files.sublist(0, limit);
        files = files.sublist(limit);
        try {
          var partialRes = await syncLocalFiles(syncFiles);
          resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
          resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
              .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
        } catch (e) {
          debugPrint(e.toString());
        }

        // Write offset
        await _writeToStorage(wal.device, wal.fileNum, 0, offset);

        // Callback
        if (updates != null) {
          updates(offset);
        }
      }
    });

    // Sync remaining files
    if (files.isNotEmpty) {
      var syncFiles = files;
      try {
        var partialRes = await syncLocalFiles(syncFiles);
        resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
        resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
            .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
      } catch (e) {
        debugPrint(e.toString());
      }

      // Write offset
      wal.storageOffset = lastOffset;
      await _writeToStorage(wal.device, wal.fileNum, 0, lastOffset);

      // Callback
      if (updates != null) {
        updates(lastOffset);
      }
    }

    // Clear file
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
    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);

    for (var i = wals.length - 1; i >= 0; i--) {
      var wal = wals[i];

      wal.isSyncing = true;
      wal.syncStartedAt = DateTime.now();
      listener.onMissingWalUpdated();

      final storageOffsetStarts = wal.storageOffset;

      var partialRes = await _syncWal(wal, (offset) {
        wal.storageOffset = offset;
        wal.syncEtaSeconds = DateTime.now().difference(wal.syncStartedAt!).inSeconds *
            (wal.storageTotalBytes - wal.storageOffset) ~/
            (wal.storageOffset - storageOffsetStarts);
        listener.onMissingWalUpdated();
      });
      resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
      resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
          .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));

      wal.status = WalStatus.synced;
      wal.isSyncing = false;
      listener.onMissingWalUpdated();
    }
    return resp;
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) async {
    var walToSync = _wals.where((w) => w == wal).toList().first;
    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);
    walToSync.isSyncing = true;
    walToSync.syncStartedAt = DateTime.now();
    listener.onMissingWalUpdated();

    final storageOffsetStarts = wal.storageOffset;

    var partialRes = await _syncWal(wal, (offset) {
      walToSync.storageOffset = offset;
      walToSync.syncEtaSeconds = DateTime.now().difference(walToSync.syncStartedAt!).inSeconds *
          (walToSync.storageTotalBytes - wal.storageOffset) ~/
          (walToSync.storageOffset - storageOffsetStarts);
      listener.onMissingWalUpdated();
    });
    resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
    resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
        .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));

    wal.status = WalStatus.synced;
    wal.isSyncing = false;
    listener.onMissingWalUpdated();
    return resp;
  }

  void setDevice(BtDevice? device) async {
    _device = device;
    _wals = await _getMissingWals();
    listener.onMissingWalUpdated();
  }
}

class LocalWalSync implements IWalSync {
  List<Wal> _wals = const [];

  List<List<int>> _frames = [];
  final HashSet<int> _syncFrameSeq = HashSet();

  Timer? _chunkingTimer;
  Timer? _flushingTimer;

  IWalSyncListener listener;

  LocalWalSync(this.listener);

  @override
  void start() {
    _wals = SharedPreferencesUtil().wals;
    debugPrint("wal service start: ${_wals.length}");
    _chunkingTimer = Timer.periodic(const Duration(seconds: chunkSizeInSeconds), (t) async {
      await _chunk();
    });
    _flushingTimer = Timer.periodic(const Duration(seconds: flushIntervalInSeconds), (t) async {
      await _flush();
    });
  }

  @override
  Future stop() async {
    _chunkingTimer?.cancel();
    _flushingTimer?.cancel();

    await _chunk();
    await _flush();

    _frames = [];
    _syncFrameSeq.clear();
    _wals = [];
  }

  Future _chunk() async {
    if (_frames.isEmpty) {
      debugPrint("Frames are empty");
      return;
    }

    var framesPerSeconds = 100;
    var lossesThreshold = 10 * framesPerSeconds; // 10s
    var newFrameSyncDelaySeconds = 15; // wait 15s for new frame synced
    var timerEnd = DateTime.now().millisecondsSinceEpoch ~/ 1000 - newFrameSyncDelaySeconds;
    var pivot = _frames.length - newFrameSyncDelaySeconds * framesPerSeconds;
    if (pivot <= 0) {
      return;
    }

    // Scan backward
    var high = pivot;
    while (high > 0) {
      var low = high - framesPerSeconds * chunkSizeInSeconds;
      if (low < 0) {
        low = 0;
      }
      var synced = true;
      var losses = 0;
      var chunk = _frames.sublist(low, high);
      for (var f in chunk) {
        var head = f.sublist(0, 3);
        var seq = Uint8List.fromList(head..add(0)).buffer.asByteData().getInt32(0);
        if (!_syncFrameSeq.contains(seq)) {
          losses++;
          if (losses >= lossesThreshold) {
            synced = false;
            break;
          }
        }
      }
      var timerStart = timerEnd - (high - low) ~/ framesPerSeconds;
      if (!synced) {
        var missWalIdx = _wals.indexWhere((w) => w.timerStart == timerStart && w.device == "phone");
        Wal missWal;
        if (missWalIdx < 0) {
          missWal = Wal(
            timerStart: timerStart,
            data: chunk,
            storage: WalStorage.mem,
            status: WalStatus.miss,
          );
          _wals.add(missWal);
        } else {
          missWal = _wals[missWalIdx];
          missWal.data.addAll(chunk);
          missWal.storage = WalStorage.mem;
          missWal.status = WalStatus.miss;
          _wals[missWalIdx] = missWal;
        }

        // send
        listener.onMissingWalUpdated();
      }

      // next
      timerEnd -= chunkSizeInSeconds;
      high = low;
    }

    debugPrint("_chunk wals ${_wals.length}");

    // clean
    _frames.removeRange(0, pivot);
  }

  Future _flush() async {
    // Storage file
    for (var i = 0; i < _wals.length; i++) {
      final wal = _wals[i];

      if (wal.storage == WalStorage.mem) {
        final directory = await getApplicationDocumentsDirectory();
        String filePath = '${directory.path}/${wal.getFileName()}';
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
        wal.filePath = filePath;
        wal.storage = WalStorage.disk;

        debugPrint("_flush file ${wal.filePath}");

        _wals[i] = wal;
      }
    }

    // Clean synced wal
    for (var i = _wals.length - 1; i >= 0; i--) {
      if (_wals[i].status == WalStatus.synced) {
        await _deleteWal(_wals[i]);
      }
    }

    SharedPreferencesUtil().wals = _wals;
  }

  Future<bool> _deleteWal(Wal wal) async {
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      try {
        final file = File(wal.filePath!);
        if (file.existsSync()) {
          await file.delete();
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
    listener.onMissingWalUpdated();
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss).toList();
  }

  void onByteStream(List<int> value) async {
    _frames.add(value);
  }

  void onBytesSync(List<int> value) {
    var head = value.sublist(0, 3);
    var seq = Uint8List.fromList(head..add(0)).buffer.asByteData().getInt32(0);
    _syncFrameSeq.add(seq);
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
    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);

    var steps = 10;
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

        debugPrint("sync wal: ${wal.id} file: ${wal.filePath}");

        try {
          File file = File(wal.filePath!);
          if (!file.existsSync()) {
            debugPrint("file ${wal.filePath} is not exists");
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
      listener.onMissingWalUpdated();
      try {
        var partialRes = await syncLocalFiles(files);

        // Ensure unique
        resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
        resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
            .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
      } catch (e) {
        debugPrint(e.toString());
        continue;
      }

      // Success? update status to synced
      for (var j = left; j < right; j++) {
        var wal = wals[j];
        wals[j].status = WalStatus.synced; // ref to _wals[]

        // Send
        listener.onWalSynced(wal);
      }

      SharedPreferencesUtil().wals = _wals;
      listener.onMissingWalUpdated();
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
    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);

    late File walFile;
    if (wal.filePath == null) {
      debugPrint("file path is not found. wal id ${wal.id}");
      wal.status = WalStatus.corrupted;
    }
    try {
      File file = File(wal.filePath!);
      if (!file.existsSync()) {
        debugPrint("file ${wal.filePath} is not exists");
        wal.status = WalStatus.corrupted;
      } else {
        walFile = file;
        wal.isSyncing = true;
      }
    } catch (e) {
      wal.status = WalStatus.corrupted;
      debugPrint(e.toString());
    }

    // Sync
    listener.onMissingWalUpdated();
    try {
      var partialRes = await syncLocalFiles([walFile]);

      // Ensure unique
      resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
      resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
          .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
    } catch (e) {
      debugPrint(e.toString());
    }

    walToSync.status = WalStatus.synced; // ref to _wals[]

    // Send
    listener.onWalSynced(wal);

    SharedPreferencesUtil().wals = _wals;
    listener.onMissingWalUpdated();

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
    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);

    // sdcard
    var partialRes = await _sdcardSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
      resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
          .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
    }

    // phone
    partialRes = await _phoneSync.syncAll(progress: progress);
    if (partialRes != null) {
      resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
      resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
          .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
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
  void onMissingWalUpdated() {
    for (var s in _subscriptions.values) {
      s.onMissingWalUpdated();
    }
  }

  @override
  void onWalSynced(Wal wal, {ServerMemory? memory}) {
    for (var s in _subscriptions.values) {
      s.onWalSynced(wal, memory: memory);
    }
  }
}
