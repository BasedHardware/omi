import 'dart:ffi';

import 'package:friend_private/backend/schema/memory.dart';

abstract class IWalService {
  void start();
  void stop();

  void subscribe(IWalServiceListener subscription, Object context);
  void unsubscribe(Object context);

  void onByteStream(List<int> value);
  void onBytesSync(List<int> value);
  Future syncAll(IWalSyncProgressListener progress);
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
  flushed,
  synced,
}

enum WalStorage {
  mem,
  disk,
}

class Wal {
  int timestamp; // ms
  String codec;
  int channel;
  int sampleRate;

  WalStatus status;
  WalStorage storage;
  String name;

  String? filePath;
  List<List<Uint8>> data = [];

  Wal(
    this.timestamp,
    this.codec,
    this.sampleRate,
    this.channel,
    this.name,
    this.status,
    this.storage, {
    this.filePath,
    this.data = const [],
  });

  // TODO: FIXME, calculate seconds
  get seconds => 10;

  static Wal mock() {
    var ts = DateTime.now().millisecondsSinceEpoch;
    return Wal(
      ts,
      "opus",
      16000,
      1,
      "${ts}_opus_1_16000",
      WalStatus.inProgress,
      WalStorage.mem,
    );
  }
}

abstract class IWalSyncProgressListener {
  void onWalSynced(Wal wal, Float percentage);
}

abstract class IWalServiceListener {
  void onStatusChanged(WalServiceStatus status);
  void onNewMissingWal(Wal wal);
  void onWalSynced(Wal wal, ServerMemory memory);
}

class WalService implements IWalService {
  final Map<Object, IWalServiceListener> _subscriptions = {};
  WalServiceStatus _status = WalServiceStatus.init;
  WalServiceStatus get status => _status;

  @override
  void subscribe(IWalServiceListener subscription, Object context) {
    _subscriptions.remove(context.hashCode);
    _subscriptions.putIfAbsent(context.hashCode, () => subscription);

    // Retains
    subscription.onStatusChanged(_status);
  }

  @override
  void unsubscribe(Object context) {
    _subscriptions.remove(context.hashCode);
  }

  @override
  void start() {
    _status = WalServiceStatus.ready;
  }

  Future _flush() async {
    // TODO: FIXME, flush from mem to disk
  }

  @override
  void stop() async {
    await _flush();

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
    // TODO: implement deleteWal
    return true;
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    // TODO: implement getMissingWals
    return [Wal.mock(), Wal.mock()];
  }

  @override
  void onByteStream(List<int> value) async {
    // TODO: implement onByteStream
  }

  @override
  void onBytesSync(List<int> value) {
    // TODO: implement onBytesSync
  }

  @override
  Future<bool> syncWal(Wal wal) async {
    // TODO: implement syncWal
    return true;
  }

  @override
  Future syncAll(IWalSyncProgressListener progress) async {
    // TODO: implement syncAll
    throw UnimplementedError();
  }
}
