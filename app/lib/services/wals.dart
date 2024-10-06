import 'dart:async';
import 'dart:collection';
import 'dart:ffi';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:path_provider/path_provider.dart';

const ChunkSizeInSeconds = 7; // 30
const FlushIntervalInSeconds = 15; //300

abstract class IWalService {
  void start();
  Future stop();

  void subscribe(IWalServiceListener subscription, Object context);
  void unsubscribe(Object context);

  void onByteStream(List<int> value);
  void onBytesSync(List<int> value);
  Future syncAll({IWalSyncProgressListener? progress});
  Future<bool> syncWal(Wal wal);
  Future<bool> deleteWal(Wal wal);
  Future<List<Wal>> getMissingWals();
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
}

enum WalStorage {
  mem,
  disk,
}

class Wal {
  int timestamp; // in seconds
  String codec;
  int channel;
  int sampleRate;

  WalStatus status;
  WalStorage storage;

  String? filePath;
  List<List<int>> data = [];

  String get id => '$timestamp';

  Wal(
      {required this.timestamp,
      this.codec = "opus",
      this.sampleRate = 16000,
      this.channel = 1,
      this.status = WalStatus.inProgress,
      this.storage = WalStorage.mem,
      this.filePath,
      this.data = const []});

  get seconds => ChunkSizeInSeconds;

  factory Wal.fromJson(Map<String, dynamic> json) {
    return Wal(
      timestamp: json['timestamp'],
      codec: json['codec'],
      channel: json['channel'],
      sampleRate: json['sample_rate'],
      status: WalStatus.values.asNameMap()[json['status']] ?? WalStatus.inProgress,
      storage: WalStorage.values.asNameMap()[json['storage']] ?? WalStorage.mem,
      filePath: json['file_path'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timestamp': timestamp,
      'codec': codec,
      'channel': channel,
      'sample_rate': sampleRate,
      'status': status.name,
      'storage': storage.name,
      'file_path': filePath,
    };
  }

  static List<Wal> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => Wal.fromJson(e)).toList();

  getFileName() {
    return "audio_${timestamp}_${codec}_${sampleRate}_$channel.bin";
  }
}

abstract class IWalSyncProgressListener {
  void onWalSyncedProgress(Wal wal, Float percentage);
}

abstract class IWalServiceListener {
  void onStatusChanged(WalServiceStatus status);
  void onNewMissingWal(Wal wal);
  void onWalSynced(Wal wal, ServerMemory memory);
}

class WalService implements IWalService {
  List<Wal> _wals = const [];

  List<List<int>> _frames = [];
  final HashSet<int> _syncFrameSeq = HashSet();

  Timer? _chunkingTimer;
  Timer? _flushingTimer;

  final Map<Object, IWalServiceListener> _subscriptions = {};
  WalServiceStatus _status = WalServiceStatus.init;
  WalServiceStatus get status => _status;

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
    _wals = SharedPreferencesUtil().wals;
    debugPrint("wal service start: ${_wals.length}");
    _chunkingTimer = Timer.periodic(const Duration(seconds: ChunkSizeInSeconds), (t) async {
      await _chunk();
    });
    _flushingTimer = Timer.periodic(const Duration(seconds: FlushIntervalInSeconds), (t) async {
      await _flush();
    });
    _status = WalServiceStatus.ready;
  }

  Future _chunk() async {
    debugPrint("_chunk");
    if (_frames.isEmpty) {
      debugPrint("Frames are empty");
      return;
    }

    var framesPerSeconds = 100;
    var ts = DateTime.now().millisecondsSinceEpoch;
    var pivot = _frames.length;
    var high = pivot;
    while (high > 0) {
      var low = high - framesPerSeconds * ChunkSizeInSeconds;
      if (low < 0) {
        low = 0;
      }
      var synced = true;
      var chunk = _frames.sublist(low, high);
      for (var f in chunk) {
        var head = f.sublist(0, 3);
        var seq = Uint8List.fromList(head..add(0)).buffer.asByteData().getInt32(0);
        if (!_syncFrameSeq.contains(seq)) {
          synced = false;
          break;
        }
      }
      debugPrint("_chunk high ${high} low ${low} - sync ${synced} - ts: ${ts ~/ 1000}");
      if (!synced) {
        var timestamp = ts ~/ 1000;
        var missWalIdx = _wals.indexWhere((w) => w.timestamp == timestamp);
        Wal missWal;
        if (missWalIdx < 0) {
          missWal = Wal(
            timestamp: timestamp,
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
        for (var sub in _subscriptions.values) {
          sub.onNewMissingWal(missWal);
        }
      }

      // next
      ts -= ChunkSizeInSeconds * 1000;
      high = low;
    }

    debugPrint("_chunk wals ${_wals.length}");

    // clean
    _frames.removeRange(0, pivot);
  }

  Future _flush() async {
    debugPrint("_flush");

    // Storage file
    for (var i = 0; i < _wals.length; i++) {
      final wal = _wals[i];

      if (wal.storage == WalStorage.mem) {
        // Flush to disk
        final directory = await getTemporaryDirectory();
        String filePath = '${directory.path}/${wal.getFileName()}';
        List<int> data = [];
        for (int i = 0; i < wal.data.length; i++) {
          var frame = wal.data[i].sublist(3);

          // Format:
          // <length>|<bytes>
          // 4 bytes |  n bytes
          final byteFrame = ByteData(4 + frame.length); // skip first 3 bytes
          byteFrame.setUint32(0, frame.length, Endian.big);
          for (int i = 0; i < frame.length; i++) {
            byteFrame.setUint8(i + 4, frame[i]);
          }
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

    SharedPreferencesUtil().wals = _wals;
  }

  @override
  Future stop() async {
    debugPrint("wal service stop");
    _chunkingTimer?.cancel();
    _flushingTimer?.cancel();

    await _chunk();
    await _flush();

    _frames = [];
    _syncFrameSeq.clear();
    _wals = [];

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
  Future<bool> deleteWal(Wal wal) async {
    // Delete file
    if (wal.filePath != null) {
      try {
        final file = File(wal.filePath!);
        await file.delete();
      } catch (e) {
        debugPrint(e.toString());
        return false;
      }
    }

    _wals.removeWhere((w) => w.id == wal.id);
    return true;
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss).toList();
  }

  @override
  void onByteStream(List<int> value) async {
    _frames.add(value);
  }

  @override
  void onBytesSync(List<int> value) {
    var head = value.sublist(0, 3);
    var seq = Uint8List.fromList(head..add(0)).buffer.asByteData().getInt32(0);
    _syncFrameSeq.add(seq);
  }

  @override
  Future<bool> syncWal(Wal wal) async {
    // TODO: implement syncWal
    return true;
  }

  @override
  Future syncAll({IWalSyncProgressListener? progress}) async {
    _wals.removeWhere((wal) => wal.status == WalStatus.synced);

    await _flush();

    var wals = _wals.where((w) => w.status == WalStatus.miss && w.storage == WalStorage.disk);
    for (var wal in wals) {
      debugPrint("sync id ${wal.id}");
      if (wal.filePath == null) {
        debugPrint("sync error: file path is not found. wal id ${wal.id}");
        continue;
      }

      try {
        File file = File(wal.filePath!);
        var bytes = await file.readAsBytes();

        // TODO: sync to socket
        debugPrint("sync wal ${wal.id} file ${wal.filePath} length ${bytes.length}");
        debugPrint("[${bytes.join(", ")}]");
      } catch (e) {
        debugPrint(e.toString());
        continue;
      }
    }
  }
}
