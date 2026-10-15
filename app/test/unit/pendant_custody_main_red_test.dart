import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/wal_file_manager.dart';

import '../support/capture/virtual_capture_time.dart';

const int _notifyAck = 0x01;
const int _notifyInfo = 0x02;
const int _cmdInfo = 0x10;
const int _cmdCustodyEnable = 0x14;

class _ScriptedTransport extends DeviceTransport {
  final ops = <Object>[];
  final writes = <List<int>>[];
  final _notify = StreamController<List<int>>.broadcast();
  final _state = StreamController<DeviceTransportState>.broadcast();

  List<int>? infoPayload;

  @override
  String get deviceId => 'omi-mainred';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    ops.add('sub:$characteristicUuid');
    return _notify.stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => const [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    ops.add('write');
    writes.add(List<int>.from(data));
    if (data[0] == _cmdInfo) {
      final info = infoPayload;
      if (info != null) _notify.add(info);
    } else if (data[0] == _cmdCustodyEnable) {
      _notify.add([_notifyAck, 0, 0x0F]);
    }
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => _state.stream;

  void emit(DeviceTransportState state) => _state.add(state);

  @override
  Future<void> dispose() async {
    await _notify.close();
    await _state.close();
  }
}

List<int> _v1InfoPayload() {
  final b = ByteData(41);
  b.setUint8(0, _notifyInfo);
  b.setUint64(1, 0, Endian.big); // read_seq
  b.setUint64(9, 64, Endian.big); // write_seq
  b.setUint32(17, 1024, Endian.big); // capacity
  b.setUint64(21, 0, Endian.big); // dropped
  b.setUint16(29, 444, Endian.big); // packet size
  b.setUint8(31, 0x0F); // advertised caps
  b.setUint8(32, 1); // contract version
  b.setUint64(33, 42, Endian.big); // ring_id
  return b.buffer.asUint8List();
}

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('custody_main_red_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('disk_space_2'),
      (MethodCall call) async {
        if (call.method == 'getFreeDiskSpaceForPath') return 4096.0;
        return null;
      },
    );
    await WalFileManager.init();
  });

  tearDown(() async {
    // The connection and WAL sync persist through the shared custody, whose
    // directory comes from the path_provider mock below; let queued checkpoint
    // writes land before the mock is removed and tempDir deleted (#20500).
    await PendantRingCustody.shared.flush();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('disk_space_2'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('capable firmware gets CMD_CUSTODY_ENABLE after INFO and before the audio subscription', () async {
    final t = _ScriptedTransport()..infoPayload = _v1InfoPayload();
    final conn = OmiDeviceConnection(
      BtDevice(id: 'omi-mainred', name: 'Omi', type: DeviceType.omi, rssi: -40, firmwareRevision: '3.0.21'),
      t,
    );
    t.emit(DeviceTransportState.connected);
    await Future<void>.delayed(const Duration(milliseconds: 80));

    final audioSub = await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await Future<void>.delayed(const Duration(milliseconds: 80));

    final writes = t.writes;
    final infoWriteAt = writes.indexWhere((w) => w[0] == _cmdInfo);
    final enableAt = writes.indexWhere((w) => w.length == 3 && w[0] == _cmdCustodyEnable && w[1] == 1 && w[2] == 0x0F);
    final audioSubAt = t.ops.indexWhere((o) => o == 'sub:19b10001-e8f2-537e-4f6c-d104768a1214');

    expect(infoWriteAt, isNonNegative, reason: 'INFO probe must precede the custody opt-in');
    expect(enableAt, isNonNegative, reason: 'capable firmware must see CMD_CUSTODY_ENABLE(0x14, 1, 0x0F)');
    expect(enableAt, greaterThan(infoWriteAt), reason: 'enable must follow a confirmed INFO');
    expect(audioSubAt, isNonNegative);
    expect(
      t.ops.indexOf('write'),
      lessThan(audioSubAt),
      reason: 'custody negotiation must precede the audio characteristic subscription',
    );

    await audioSub?.cancel();
    await conn.disconnect();
    await t.dispose();
  });

  test('pendant BLE frames drain to disk within the 10s custody window', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final sync = LocalWalSyncImpl(
      _Listener(),
      periodic: scheduler.periodic,
      persistWals: WalFileManager.saveWals,
    );
    sync.setDeviceInfo('dev', 'Omi');
    sync.start();
    try {
      await sync.walReady;

      for (var i = 0; i < 1000; i++) {
        final syncKey = FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF, 0]);
        sync.onFrameCaptured(WalFrame(payload: [0xAA, i & 0xFF], syncKey: syncKey));
      }

      // Fire only what comes due inside the 10s window; the 75s/105s batch timers stay pending.
      scheduler.elapse(const Duration(seconds: 10));
      expect(
        scheduler.pendingTimers.where((t) => t.fires > 0),
        isNotEmpty,
        reason: 'a pendant drain timer must fire within 10s — the 75s/105s batch timers cannot prove custody',
      );
      // Await the Future the drain callback returned (audio write, then WAL index save) instead of
      // a fixed sleep: under CI load a 300 ms sleep ended before the index save landed (#20500).
      await scheduler.waitForCallbackIo();

      final wals = await WalFileManager.loadWals();
      expect(
        wals.where((w) => w.storage == WalStorage.disk),
        isNotEmpty,
        reason: 'pendant frames must reach the disk index inside the custody window',
      );
      final wal = wals.firstWhere((w) => w.storage == WalStorage.disk);
      expect(
        File('${tempDir.path}/${wal.filePath}').existsSync(),
        isTrue,
        reason: 'the audio file must be durable, not just the index entry',
      );
    } finally {
      // stop() queues behind any drain still running, so its WAL index write lands before tearDown
      // deletes tempDir even when an expectation above failed (#20500).
      await sync.stop();
    }
  });

  test('a full ring of 723 pending disk WALs is never evicted and flags retention risk', () async {
    final wals = <Wal>[];
    for (var i = 0; i < 723; i++) {
      final name = 'pending_$i.bin';
      File('${tempDir.path}/$name').writeAsBytesSync([i & 0xFF]);
      wals.add(
        Wal(
          codec: BleAudioCodec.opus,
          timerStart: 1700000000 + i,
          seconds: 1,
          totalFrames: 1,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          device: 'dev',
          filePath: name,
        ),
      );
    }
    final sync = LocalWalSyncImpl(_Listener(), persistWals: WalFileManager.saveWals);
    sync.testWals = wals;
    final names = wals.map((w) => w.filePath!).toList();
    const expectedCount = 723;

    await sync.enforceRetentionPolicyForTesting();

    final missing = names.where((n) => !File('${tempDir.path}/$n').existsSync()).toList();
    expect(missing, isEmpty, reason: 'pending (unsynced) copies must never be evicted to satisfy the count cap');
    expect(sync.testWals.length, expectedCount, reason: 'every pending WAL must remain retained');
    await WalFileManager.saveWals(List.of(sync.testWals));
    final index = await WalFileManager.loadWals();
    expect(index.length, expectedCount, reason: 'the index must keep every pending WAL');
    expect(
      sync.retentionRisk,
      isNotNull,
      reason: 'the cap overflow must surface as retention risk, not silent deletion',
    );

    await sync.stop();
  });
}
