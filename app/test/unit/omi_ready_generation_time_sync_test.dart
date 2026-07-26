import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _ReadyFakeTransport transport;
  late OmiDeviceConnection connection;
  late int clockTick;

  setUp(() {
    clockTick = 0;
    transport = _ReadyFakeTransport();
    connection = OmiDeviceConnection(
      BtDevice(name: 'Omi', id: 'fake-omi', type: DeviceType.omi, rssi: -40),
      transport,
      now: () => DateTime.utc(2026, 7, 25, 12, 0, clockTick++),
    );
  });

  tearDown(() async {
    await connection.disconnect();
    await transport.dispose();
  });

  test('initial connect syncs once even though connect and ready observe the same generation', () async {
    await connection.connect();
    await _waitFor(() => transport.timeWrites.length == 1);

    expect(transport.timeWrites, [_epoch(DateTime.utc(2026, 7, 25, 12))]);

    transport.emitCurrentReadyGenerationAgain();
    await pumpEventQueue();
    expect(transport.timeWrites, hasLength(1));
  });

  test('native reconnect syncs every new ready generation after an earlier write error', () async {
    transport.failNextTimeWrite = true;
    await connection.connect();
    expect(transport.timeWriteAttempts, 1);
    expect(transport.timeWrites, isEmpty);

    transport.emitReconnect();
    await _waitFor(() => transport.timeWrites.length == 1);

    expect(transport.timeWriteAttempts, 2);
    expect(transport.timeWrites.single, _epoch(DateTime.utc(2026, 7, 25, 12, 0, 1)));
  });

  test('stale generations are serialized so an older clock write cannot finish last', () async {
    await connection.connect();
    final secondGenerationGate = Completer<void>();
    transport.nextTimeWriteGate = secondGenerationGate;

    transport.emitReconnect();
    await _waitFor(() => transport.timeWriteAttempts == 2);
    expect(transport.activeTimeWrites, 1);

    transport.emitReconnect();
    await pumpEventQueue();
    expect(transport.timeWriteAttempts, 2, reason: 'generation 3 must wait behind generation 2');

    secondGenerationGate.complete();
    await _waitFor(() => transport.timeWriteAttempts == 3);
    await _waitFor(() => transport.activeTimeWrites == 0);

    expect(transport.maxConcurrentTimeWrites, 1);
    expect(
      transport.timeWrites,
      [
        _epoch(DateTime.utc(2026, 7, 25, 12)),
        _epoch(DateTime.utc(2026, 7, 25, 12, 0, 1)),
        _epoch(DateTime.utc(2026, 7, 25, 12, 0, 2)),
      ],
    );
  });
}

int _epoch(DateTime value) => value.millisecondsSinceEpoch ~/ 1000;

Future<void> _waitFor(bool Function() condition) async {
  for (var i = 0; i < 20; i++) {
    if (condition()) return;
    await pumpEventQueue();
  }
  expect(condition(), isTrue);
}

class _ReadyFakeTransport extends DeviceTransport implements DeviceReadyGenerationSource {
  final _stateController = StreamController<DeviceTransportState>.broadcast();
  final _readyController = StreamController<int>.broadcast();
  final List<int> timeWrites = [];

  @override
  int readyGeneration = 0;

  int timeWriteAttempts = 0;
  int activeTimeWrites = 0;
  int maxConcurrentTimeWrites = 0;
  bool failNextTimeWrite = false;
  Completer<void>? nextTimeWriteGate;
  bool _connected = false;

  @override
  String get deviceId => 'fake-omi';

  @override
  Stream<DeviceTransportState> get connectionStateStream => _stateController.stream;

  @override
  Stream<int> get readyGenerationStream => _readyController.stream;

  @override
  Future<void> connect() async {
    _stateController.add(DeviceTransportState.connecting);
    _emitReady();
  }

  void emitReconnect() {
    _connected = false;
    _stateController.add(DeviceTransportState.disconnected);
    _stateController.add(DeviceTransportState.connecting);
    _emitReady();
  }

  void emitCurrentReadyGenerationAgain() {
    _readyController.add(readyGeneration);
  }

  void _emitReady() {
    _connected = true;
    readyGeneration++;
    _stateController.add(DeviceTransportState.connected);
    _readyController.add(readyGeneration);
  }

  @override
  Future<void> disconnect() async {
    if (!_connected) return;
    _connected = false;
    _stateController.add(DeviceTransportState.disconnected);
  }

  @override
  Future<void> dispose() async {
    await _stateController.close();
    await _readyController.close();
  }

  @override
  Future<bool> isConnected() async => _connected;

  @override
  Future<bool> ping() async => _connected;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => const [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    timeWriteAttempts++;
    activeTimeWrites++;
    maxConcurrentTimeWrites = activeTimeWrites > maxConcurrentTimeWrites ? activeTimeWrites : maxConcurrentTimeWrites;
    try {
      if (failNextTimeWrite) {
        failNextTimeWrite = false;
        throw StateError('simulated GATT write failure');
      }
      final gate = nextTimeWriteGate;
      nextTimeWriteGate = null;
      if (gate != null) await gate.future;
      timeWrites.add(ByteData.sublistView(Uint8List.fromList(data)).getUint32(0, Endian.little));
    } finally {
      activeTimeWrites--;
    }
  }
}
