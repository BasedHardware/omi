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

const chunkSizeInSeconds = 30;
const flushIntervalInSeconds = 60;

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
  int byteOffset = 0;

  bool isSyncing = false;

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
      this.byteOffset = 0,
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
      seconds: json['seconds'] ?? 30,
      device: json['device'] ?? "phone",
      byteOffset: json['byte_offset'] ?? 0,
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
      'byte_offset': byteOffset,
    };
  }

  static List<Wal> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => Wal.fromJson(e)).toList();

  getFileName() {
    return "audio_${device.toLowerCase().replaceAll(RegExp(r'^[a-z0-9]'), "")}_${codec}_${sampleRate}_${channel}_${timerStart}.bin";
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
    // Soft delete
    // TODO: Delete from sdcard
    _wals.removeWhere((w) => w.id == wal.id);
    listener.onMissingWalUpdated();
  }

  Future<List<Wal>> _getMissingWals() async {
    if (_device == null) {
      return [];
    }
    var storageFiles = await _getStorageList(_device!.id);
    if (storageFiles.isEmpty) {
      return [];
    }
    var totalBytes = storageFiles[0];
    if (totalBytes <= 0) {
      return [];
    }
    debugPrint(" _getMissingWals > ${storageFiles.map((m) => m.toString())}");

    // Chunking backward
    var timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    var storageByteOffset = totalBytes;
    List<Wal> wals = [];
    while (storageByteOffset > 0) {
      timerStart -= chunkSizeInSeconds;
      storageByteOffset -= chunkSizeInSeconds * 100 * 80; // 80: frame length, 100: frame per seconds
      if (storageByteOffset < 0) {
        storageByteOffset = 0;
      }
      wals.add(Wal(
        timerStart: timerStart,
        status: WalStatus.miss,
        storage: WalStorage.sdcard,
        seconds: chunkSizeInSeconds,
        byteOffset: storageByteOffset,
        device: _device!.id,
      ));
    }

    return wals;
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals;
  }

  @override
  Future start() async {
    _wals = await _getMissingWals();
    listener.onMissingWalUpdated(); // TODO: FIXME
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

  Future<File?> _readStorageBytesToFile(Wal wal) async {
    var deviceId = wal.device;

    // Move the offset to wal.byteOffset
    int command = 0;
    int fileNum = 1;
    int offset = wal.byteOffset;
    int limit = wal.seconds * 100; // 100 frames per sec

    debugPrint("_readStorageBytesToFile ${offset}");
    await _writeToStorage(deviceId, fileNum, command, offset);

    // read
    List<List<int>> bytesData = [];
    await _storageStream?.cancel();
    final completer = Completer<bool>();
    _storageStream = await _getBleStorageBytesListener(deviceId, onStorageBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;

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
          completer.complete(true);
        } else if (value[0] == 100) {
          // valid end command
          debugPrint('end');
          completer.complete(true);
        } else {
          // bad bit
          debugPrint('Error bit returned');
          completer.complete(true);
        }
        return;
      }
      if (value.length < 20) {
        // TODO: FIXME
        return;
      }

      //debugPrint("read ${offset} > current ${bytesData.length} / ${limit}");

      bytesData.add(value);
      if (bytesData.length >= limit) {
        // done
        await _storageStream?.cancel();
        completer.complete(true);
      }
    });
    await completer.future;
    if (bytesData.isEmpty) {
      debugPrint("_readStorageBytesToFile empty bytes");
      return null;
    }

    // Write to file
    final directory = await getApplicationDocumentsDirectory();
    String filePath = '${directory.path}/${wal.getFileName()}';
    List<int> data = [];
    for (int i = 0; i < bytesData.length; i++) {
      var frame = bytesData[i].sublist(3);

      // Format:
      // <length>|<bytes>
      // 4 bytes |  n bytes
      final byteFrame = ByteData(frame.length);
      // Check why 37 -> [0, 0, 0, 37] ???
      // byteFrame.setUint32(0, frame.length, Endian.big);
      for (int i = 0; i < frame.length; i++) {
        byteFrame.setUint8(i, frame[i]);
      }
      data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());
    }
    final file = File(filePath);
    await file.writeAsBytes(data);

    debugPrint("_readStorageBytesToFile ${offset} file ${filePath}");

    return file;
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.sdcard).toList();
    if (wals.isEmpty) {
      debugPrint("All synced!");
      return null;
    }

    // Empty resp
    var resp = SyncLocalFilesResponse(newMemoryIds: [], updatedMemoryIds: []);

    var steps = 3;
    var left = 0;
    while (left < wals.length) {
      var right = left + steps;
      if (right >= wals.length) {
        right = wals.length;
      }
      List<File> files = [];
      for (var j = left; j < right; j++) {
        var wal = wals[j];
        debugPrint("sync wal: ${wal.id} byte offset: ${wal.byteOffset} ts ${wal.timerStart}");

        try {
          // due to slow reading from ble
          wal.isSyncing = true;
          listener.onMissingWalUpdated();

          File? file = await _readStorageBytesToFile(wal);
          if (file == null || !file.existsSync()) {
            debugPrint("file null or ${file?.path} is not exists");
            wal.status = WalStatus.corrupted;
            continue;
          }
          files.add(file);
        } catch (e) {
          wal.status = WalStatus.corrupted;
          debugPrint(e.toString());
        }
      }

      if (files.isEmpty) {
        debugPrint("Files are empty");

        // next
        left = right;
        continue;
      }

      // Progress
      progress?.onWalSyncedProgress((left).toDouble() / wals.length);

      // Sync
      try {
        var partialRes = await syncLocalFiles(files);

        // Ensure unique
        resp.newMemoryIds.addAll(partialRes.newMemoryIds.where((id) => !resp.newMemoryIds.contains(id)));
        resp.updatedMemoryIds.addAll(partialRes.updatedMemoryIds
            .where((id) => !resp.updatedMemoryIds.contains(id) && !resp.newMemoryIds.contains(id)));
      } catch (e) {
        debugPrint(e.toString());

        // next
        left = right;
        continue;
      }

      // Success? update status to synced
      for (var j = left; j < right; j++) {
        var wal = wals[j];
        wals[j].status = WalStatus.synced; // ref to _wals[]

        // Send
        listener.onWalSynced(wal);
      }

      // next
      left = right;

      SharedPreferencesUtil().wals = _wals;
      listener.onMissingWalUpdated();
    }

    // Progress
    progress?.onWalSyncedProgress(1.0);
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
    var lossesThreshold = 3 * framesPerSeconds; // 3s
    var newFrameSyncDelaySeconds = 5; // wait 5s for new frame synced
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
      debugPrint("_chunk high: ${high} low: ${low} sync: ${synced} timerEnd: ${timerEnd} timerStart: ${timerStart}");
      if (!synced) {
        var missWalIdx = _wals.indexWhere((w) => w.timerStart == timerStart);
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

          // Format:
          // <length>|<bytes>
          // 4 bytes |  n bytes
          final byteFrame = ByteData(frame.length);
          // Check why 37 -> [0, 0, 0, 37] ???
          // byteFrame.setUint32(0, frame.length, Endian.big);
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
    var right = wals.length;
    while (right > 0) {
      var left = right - steps;
      if (left < 0) {
        left = 0;
      }
      List<File> files = [];
      for (var j = right - 1; j >= left; j--) {
        var wal = wals[j];
        debugPrint("sync id ${wal.id}");
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

            right = left;
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

        // next
        right = left;
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

        // next
        right = left;
        continue;
      }

      // Success? update status to synced
      for (var j = left; j < right; j++) {
        var wal = wals[j];
        wals[j].status = WalStatus.synced; // ref to _wals[]

        // Send
        listener.onWalSynced(wal);
      }

      // next
      right = left;

      SharedPreferencesUtil().wals = _wals;
      listener.onMissingWalUpdated();
    }

    // Progress
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
    //return await _phoneSync.syncAll(progress: progress);
    return await _sdcardSync.syncAll(progress: progress);
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
