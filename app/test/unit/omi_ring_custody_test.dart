import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';

class _ScriptedTransport extends DeviceTransport {
  _ScriptedTransport({
    required this.infoPayload,
    this.enableStatus = 0,
    this.grantedCaps,
    this.advanceStatus = 0,
    this.dropEnableAck = false,
  });

  final List<int>? infoPayload;
  final int enableStatus;
  final int? grantedCaps;
  final int advanceStatus;
  final bool dropEnableAck;

  final writes = <List<int>>[];
  final subscribes = <String>[];
  Completer<void>? holdEnableAck;
  final _notify = StreamController<List<int>>.broadcast();
  final _state = StreamController<DeviceTransportState>.broadcast();

  void Function(List<int> write)? onWrite;

  @override
  String get deviceId => 'omi-1';

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
    subscribes.add(characteristicUuid);
    return _notify.stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => const [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add(List<int>.from(data));
    onWrite?.call(data);
    switch (data[0]) {
      case RingProtocol.cmdInfo:
        final info = infoPayload;
        if (info != null) _notify.add(info);
      case RingProtocol.cmdCustodyEnable:
        if (dropEnableAck) break;
        final held = holdEnableAck;
        void sendAck() => _notify.add(
              grantedCaps != null
                  ? [RingProtocol.notifyAck, enableStatus, grantedCaps!]
                  : [RingProtocol.notifyAck, enableStatus],
            );
        if (held != null) {
          unawaited(held.future.then((_) => sendAck()));
          break;
        }
        sendAck();
      case RingProtocol.cmdAdvance:
      case RingProtocol.cmdAdvanceId:
        _notify.add([RingProtocol.notifyAck, advanceStatus]);
    }
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => _state.stream;

  void emit(DeviceTransportState state) => _state.add(state);

  void notify(List<int> value) => _notify.add(value);

  @override
  Future<void> dispose() async {
    await _notify.close();
    await _state.close();
  }
}

List<int> _v1Info({int caps = 0x0F, int ringId = 0x1122334455667788, int readSeq = 0}) {
  final b = ByteData(41);
  b.setUint8(0, RingProtocol.notifyInfo);
  b.setUint64(1, readSeq, Endian.big);
  b.setUint64(9, 64, Endian.big); // writeSeq
  b.setUint32(17, 1024, Endian.big);
  b.setUint64(21, 0, Endian.big);
  b.setUint16(29, 444, Endian.big);
  b.setUint8(31, caps);
  b.setUint8(32, RingProtocol.custodyContractVersion);
  b.setUint64(33, ringId, Endian.big);
  return b.buffer.asUint8List();
}

RingInfo _ringInfo({int ringId = 0x1122334455667788, int readSeq = 0, int writeSeq = 64}) => RingInfo(
      readSeq: readSeq,
      writeSeq: writeSeq,
      capacityPackets: 1024,
      droppedPackets: 0,
      packetSize: 444,
      advertisedCaps: 0x0F,
      contractVersion: 1,
      ringId: ringId,
      infoBytes: 41,
    );

List<int> _legacyInfo() {
  final b = ByteData(31);
  b.setUint8(0, RingProtocol.notifyInfo);
  b.setUint64(1, 0, Endian.big);
  b.setUint64(9, 64, Endian.big);
  b.setUint32(17, 1024, Endian.big);
  b.setUint64(21, 0, Endian.big);
  b.setUint16(29, 444, Endian.big);
  return b.buffer.asUint8List();
}

BtDevice _device(String fw) =>
    BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40, firmwareRevision: fw);

Future<void> _settle() => Future<void>.delayed(const Duration(milliseconds: 50));

bool _hasOp(_ScriptedTransport t, int op) => t.writes.any((w) => w[0] == op);

/// Ends the custody session, then waits for every queued checkpoint write, so no
/// write outlives the directory the test is about to delete (#20500).
Future<void> _drainCustody(OmiDeviceConnection? conn, Iterable<PendantRingCustody> custodies) async {
  await conn?.disconnect();
  for (final custody in custodies) {
    await custody.flush();
  }
}

void main() {
  test(
    'ring firmware >= 3.0.20 probes INFO at connect; 0x14 opt-in only once a real audio listener attaches',
    () async {
      final t = _ScriptedTransport(infoPayload: _v1Info(), grantedCaps: 0x0F);
      final conn = OmiDeviceConnection(_device('3.0.21'), t);
      t.emit(DeviceTransportState.connected);
      await _settle();

      expect(_hasOp(t, RingProtocol.cmdInfo), isTrue);
      expect(conn.lastRingInfo, isNotNull);
      expect(_hasOp(t, RingProtocol.cmdCustodyEnable), isFalse);
      expect(conn.ringLivePersistEnabled, isFalse);

      final audioSub = await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
      await _settle();

      final enable = t.writes.firstWhere((w) => w[0] == RingProtocol.cmdCustodyEnable);
      expect(enable, [0x14, 0x01, 0x0F]);
      expect(conn.ringLivePersistEnabled, isTrue);
      await audioSub?.cancel();
    },
  );

  test('legacy 31-byte INFO never sends the new custody opcode', () async {
    final t = _ScriptedTransport(infoPayload: _legacyInfo());
    OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();

    expect(_hasOp(t, RingProtocol.cmdInfo), isTrue);
    expect(_hasOp(t, RingProtocol.cmdCustodyEnable), isFalse);
  });

  test('firmware 3.0.19 never sees a ring opcode', () async {
    final t = _ScriptedTransport(infoPayload: _v1Info());
    OmiDeviceConnection(_device('3.0.19'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();

    expect(t.writes, isEmpty);
  });

  test('INVALID_COMMAND on enable keeps the connection legacy — advance uses 0x12', () async {
    final t = _ScriptedTransport(infoPayload: _v1Info(), enableStatus: RingProtocol.ackInvalidCommand);
    final conn = OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();
    await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();
    expect(conn.ringLivePersistEnabled, isFalse);
    expect(conn.ringEffectiveCaps, 0);

    final ack = await conn.advanceRingCustody(7, expectedEpoch: conn.ringCustodyEpoch, expectedRingId: null);
    expect(ack?.isOk, isTrue);
    final advance = t.writes.last;
    expect(advance[0], RingProtocol.cmdAdvance); // 0x12, not 0x15
  });

  test(
    'a lost ENABLE ack keeps ring-id custody; a stale-ring advance is fenced with status 11 and no wire write',
    () async {
      const ringA = 0x1122334455667788;
      const ringB = 0x0102030405060708;
      final t = _ScriptedTransport(infoPayload: _v1Info(ringId: ringA), dropEnableAck: true);
      final conn = OmiDeviceConnection(_device('3.0.21'), t);
      t.emit(DeviceTransportState.connected);
      await _settle();
      await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
      await Future<void>.delayed(const Duration(seconds: 6));

      expect(conn.ringEffectiveCaps & RingProtocol.capRingId, RingProtocol.capRingId);
      expect(conn.ringEffectiveCaps & RingProtocol.capLivePersist, 0);
      expect(conn.ringLivePersistEnabled, isFalse);

      t.notify(_v1Info(ringId: ringB, readSeq: 0));
      await _settle();
      final before = t.writes.length;
      final ack = await conn.advanceRingCustody(1, expectedEpoch: conn.ringCustodyEpoch, expectedRingId: ringA);
      expect(ack?.status, RingProtocol.ackRingIdMismatch);
      expect(
        t.writes.length,
        before,
        reason: 'no 0x12 or 0x15 may leave the transport for a proof captured under ring A',
      );
    },
  );

  test('armed CAP_RING_ID advance sends 0x15 [ringId u64 BE][seq u64 BE]', () async {
    const ringId = 0x1122334455667788;
    final t = _ScriptedTransport(infoPayload: _v1Info(ringId: ringId), grantedCaps: 0x0F);
    final conn = OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();
    await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();

    await conn.advanceRingCustody(42, expectedEpoch: conn.ringCustodyEpoch, expectedRingId: ringId);
    final advance = t.writes.last;
    expect(advance[0], RingProtocol.cmdAdvanceId);
    expect(advance.length, 17);
    final bd = ByteData.sublistView(Uint8List.fromList(advance));
    expect(bd.getUint64(1, Endian.big), ringId);
    expect(bd.getUint64(9, Endian.big), 42);
  });

  test('RING_ID_MISMATCH ack surfaces status 11 with no 0x12 fallback retry', () async {
    final t = _ScriptedTransport(
      infoPayload: _v1Info(),
      grantedCaps: 0x0F,
      advanceStatus: RingProtocol.ackRingIdMismatch,
    );
    final conn = OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();
    await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();

    final ack = await conn.advanceRingCustody(
      10,
      expectedEpoch: conn.ringCustodyEpoch,
      expectedRingId: 0x1122334455667788,
    );
    expect(ack?.status, RingProtocol.ackRingIdMismatch);
    expect(_hasOp(t, RingProtocol.cmdAdvance), isFalse);
  });

  test('physical reconnect bumps the epoch and re-arms the custody probe', () async {
    final t = _ScriptedTransport(infoPayload: _v1Info(), grantedCaps: 0x0F);
    final conn = OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();
    await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();
    expect(conn.ringLivePersistEnabled, isTrue);
    final epoch1 = conn.ringCustodyEpoch;

    t.emit(DeviceTransportState.disconnected);
    await _settle();
    expect(conn.ringLivePersistEnabled, isFalse);
    expect(conn.lastRingInfo, isNull);

    t.emit(DeviceTransportState.connected);
    await _settle();
    expect(conn.ringCustodyEpoch, epoch1 + 1);
    expect(t.writes.where((w) => w[0] == RingProtocol.cmdInfo).length, greaterThanOrEqualTo(2));
    expect(
      t.writes.where((w) => w[0] == RingProtocol.cmdCustodyEnable).length,
      greaterThanOrEqualTo(2),
      reason: 'a surviving audio subscriber re-opts-in once per physical epoch without re-attaching',
    );
    expect(conn.ringLivePersistEnabled, isTrue);
  });

  test('INFO observed on the wire registers the ring incarnation with the custody manager', () async {
    const ringId = 0x1122334455667788;
    final t = _ScriptedTransport(infoPayload: _v1Info(ringId: ringId), grantedCaps: 0x0F);
    OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();

    expect(PendantRingCustody.shared.currentRingId('omi-1'), ringId);
  });

  test('persisted durable frontier replays before READ through 0x15 only', () async {
    const ringId = 0x1122334455667788;
    final tmp = await Directory.systemTemp.createTemp('custody_replay_test');
    OmiDeviceConnection? conn;
    final custodies = <PendantRingCustody>[];
    try {
      final store = PendantCustodyStore(directoryProvider: () async => tmp);
      final seed = PendantRingCustody(store: store, walValidator: (_) async => true);
      custodies.add(seed);
      await seed.beginConnection('omi-1', 1, _ringInfo(ringId: ringId));
      await seed.recordDurableRingRange('omi-1', 1, ringId, 0, 10, const [
        CustodyWalRef(fileName: 'a.bin', bytes: 1, frames: 1),
      ]);

      final custody = PendantRingCustody(store: store, walValidator: (_) async => true);
      custodies.add(custody);
      final t = _ScriptedTransport(infoPayload: _v1Info(ringId: ringId), grantedCaps: 0x0F);
      conn = OmiDeviceConnection(_device('3.0.21'), t, custody: custody);
      t.emit(DeviceTransportState.connected);
      await _settle();

      final advances =
          t.writes.where((w) => w[0] == RingProtocol.cmdAdvance || w[0] == RingProtocol.cmdAdvanceId).toList();
      expect(advances, hasLength(1));
      expect(advances.single[0], RingProtocol.cmdAdvanceId);
      final bd = ByteData.sublistView(Uint8List.fromList(advances.single));
      expect(bd.getUint64(1, Endian.big), ringId);
      expect(bd.getUint64(9, Endian.big), 10);
      expect(_hasOp(t, RingProtocol.cmdAdvance), isFalse);
    } finally {
      await _drainCustody(conn, custodies);
      if (await tmp.exists()) await tmp.delete(recursive: true);
    }
  });

  test('rejected opt-in suppresses the persisted replay entirely', () async {
    const ringId = 0x1122334455667788;
    final tmp = await Directory.systemTemp.createTemp('custody_reject_test');
    OmiDeviceConnection? conn;
    final custodies = <PendantRingCustody>[];
    try {
      final store = PendantCustodyStore(directoryProvider: () async => tmp);
      final seed = PendantRingCustody(store: store, walValidator: (_) async => true);
      custodies.add(seed);
      await seed.beginConnection('omi-1', 1, _ringInfo(ringId: ringId));
      await seed.recordDurableRingRange('omi-1', 1, ringId, 0, 10, const [
        CustodyWalRef(fileName: 'a.bin', bytes: 1, frames: 1),
      ]);

      final custody = PendantRingCustody(store: store, walValidator: (_) async => true);
      custodies.add(custody);
      final t = _ScriptedTransport(
        infoPayload: _v1Info(ringId: ringId),
        enableStatus: RingProtocol.ackInvalidCommand,
      );
      final connection = OmiDeviceConnection(_device('3.0.21'), t, custody: custody);
      conn = connection;
      t.emit(DeviceTransportState.connected);
      await _settle();
      expect(t.writes.where((w) => w[0] == RingProtocol.cmdInfo), isNotEmpty);

      await connection.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
      await _settle();

      expect(connection.ringEffectiveCaps, 0);
      expect(connection.ringLivePersistEnabled, isFalse);
      final writesBefore = t.writes.length;
      final fenced = await connection.advanceRingCustody(
        10,
        expectedEpoch: connection.ringCustodyEpoch,
        expectedRingId: ringId,
      );
      expect(fenced?.status, RingProtocol.ackRingIdMismatch);
      expect(t.writes.length, writesBefore);
      expect(_hasOp(t, RingProtocol.cmdAdvance), isFalse);
    } finally {
      await _drainCustody(conn, custodies);
      if (await tmp.exists()) await tmp.delete(recursive: true);
    }
  });

  test('INFO ring-id change fences a queued advance — no retagged 0x15', () async {
    const ringA = 0x1122334455667788;
    const ringB = 0x0102030405060708;
    final t = _ScriptedTransport(infoPayload: _v1Info(ringId: ringA), grantedCaps: 0x0F);
    final conn = OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();
    final writesBefore = t.writes.length;

    t.notify(_v1Info(ringId: ringB));
    await _settle();

    final ack = await conn.advanceRingCustody(
      10,
      expectedEpoch: conn.ringCustodyEpoch,
      expectedRingId: ringA, // proof captured under the OLD incarnation
    );
    expect(ack?.status, RingProtocol.ackRingIdMismatch);
    expect(t.writes.length, writesBefore);
    expect(_hasOp(t, RingProtocol.cmdAdvanceId), isFalse);
  });

  test('unknown firmware at connect probes once metadata is populated', () async {
    final t = _ScriptedTransport(infoPayload: _v1Info(), grantedCaps: 0x0F);
    final device = _device('Unknown');
    final conn = OmiDeviceConnection(device, t);
    t.emit(DeviceTransportState.connected);
    await _settle();
    expect(_hasOp(t, RingProtocol.cmdInfo), isFalse);

    device.firmwareRevision = '3.0.21';
    await conn.retryRingCustodyProbe();
    await _settle();
    expect(_hasOp(t, RingProtocol.cmdInfo), isTrue);
    expect(_hasOp(t, RingProtocol.cmdCustodyEnable), isFalse);
    await conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();
    expect(_hasOp(t, RingProtocol.cmdCustodyEnable), isTrue);
  });

  test('a concurrent audio attach during a held ENABLE joins the in-flight opt-in', () async {
    const audioUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';
    final t = _ScriptedTransport(infoPayload: _v1Info(), grantedCaps: 0x0F)..holdEnableAck = Completer<void>();
    final conn = OmiDeviceConnection(_device('3.0.21'), t);
    t.emit(DeviceTransportState.connected);
    await _settle();

    final first = conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();
    final second = conn.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});
    await _settle();

    expect(
      t.writes.where((w) => w[0] == RingProtocol.cmdCustodyEnable),
      hasLength(1),
      reason: 'the second attach must join the held opt-in, not send another 0x14',
    );
    expect(
      t.subscribes.where((c) => c == audioUuid),
      isEmpty,
      reason: 'no audio characteristic subscription while the enable ACK is in flight',
    );

    t.holdEnableAck!.complete();
    final s1 = await first;
    final s2 = await second;
    await _settle();
    expect(conn.ringLivePersistEnabled, isTrue);
    expect(t.subscribes.where((c) => c == audioUuid), hasLength(2));
    await s1?.cancel();
    await s2?.cancel();
  });

  test('explicit disconnect ends the custody session even without a transport event', () async {
    const ringId = 0x1122334455667788;
    final tmp = await Directory.systemTemp.createTemp('custody_disconnect_test');
    PendantRingCustody? custody;
    try {
      custody = PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => tmp),
        walValidator: (_) async => true,
      );
      final t = _ScriptedTransport(infoPayload: _v1Info(ringId: ringId), grantedCaps: 0x0F);
      final conn = OmiDeviceConnection(_device('3.0.21'), t, custody: custody);
      t.emit(DeviceTransportState.connected);
      await _settle();
      expect(custody.currentRingId('omi-1'), ringId);
      final epoch = conn.ringCustodyEpoch;

      await conn.disconnect();
      await _settle();
      expect(custody.hasConnection('omi-1', epoch), isFalse);
      expect(custody.currentRingId('omi-1'), isNull);
    } finally {
      await custody?.flush();
      if (await tmp.exists()) await tmp.delete(recursive: true);
    }
  });
}
