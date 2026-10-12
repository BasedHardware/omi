import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _TrackingTransport extends DeviceTransport {
  bool connected = false;
  int disconnectCalls = 0;
  int disposeCalls = 0;

  @override
  String get deviceId => 'limitless-1';

  @override
  Future<void> connect() async => connected = true;

  @override
  Future<void> disconnect() async {
    connected = false;
    disconnectCalls++;
  }

  @override
  Future<void> dispose() async => disposeCalls++;

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<bool> ping() async => connected;

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => const [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}
}

class _FailsAfterGattLinkConnection extends DeviceConnection {
  _FailsAfterGattLinkConnection(super.device, super.transport);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  @override
  Future<void> connect({void Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await transport.connect();
    connectionState = DeviceConnectionState.connected;
    throw StateError('protected initialization failed');
  }

  @override
  Future<int> performRetrieveBatteryLevel() async => -1;

  @override
  Future<List<int>> performGetButtonState() async => const [];
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('failed device initialization tears down the partial GATT link and clears the cached connection', () async {
    final device = BtDevice(
      id: 'limitless-1',
      name: 'Pendant',
      type: DeviceType.limitless,
      rssi: -46,
      locator: DeviceLocator.bluetooth(deviceId: 'limitless-1'),
    );
    await SharedPreferencesUtil().btDeviceSet(device);

    final transport = _TrackingTransport();
    final failedConnection = _FailsAfterGattLinkConnection(device, transport);
    final service = DeviceService(connectionBuilder: (_) => failedConnection);

    await expectLater(service.ensureConnection(device.id, force: true), throwsStateError);

    expect(transport.disconnectCalls, 1);
    expect(transport.disposeCalls, 1);
    expect(await service.ensureConnection(device.id), isNull);
  });

  test('launch timeout preserves the connection and transport for native background reconnection', () async {
    final device = BtDevice(
      id: 'omi-pendant-1',
      name: 'Omi Pendant',
      type: DeviceType.omi,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: 'omi-pendant-1'),
    );
    await SharedPreferencesUtil().btDeviceSet(device);

    final transport = _TimingOutTransport();
    final connection = _TimingOutConnection(device, transport);
    final service = DeviceService(connectionBuilder: (_) => connection);

    // Initial connection attempt times out
    final initialResult = await service.ensureConnection(device.id, force: true);
    expect(initialResult, isNull);

    // Transport and connection must NOT be disposed or disconnected
    expect(transport.disconnectCalls, 0);
    expect(transport.disposeCalls, 0);
    expect(service.connectionFor(device.id), same(connection));
    expect(connection.status, DeviceConnectionState.disconnected);

    // Later native event brings the device back in range
    transport.emitConnected();
    expect(connection.status, DeviceConnectionState.connected);

    // When connection is up, ensureConnection cleanly returns the existing connection
    final reconnected = await service.ensureConnection(device.id);
    expect(reconnected, same(connection));
  });
}

class _TimingOutTransport extends _TrackingTransport {
  final _stateController = StreamController<DeviceTransportState>.broadcast();

  @override
  Stream<DeviceTransportState> get connectionStateStream => _stateController.stream;

  @override
  Future<void> connect() async {
    throw TimeoutException('Device ready timeout after 60s');
  }

  void emitConnected() {
    connected = true;
    _stateController.add(DeviceTransportState.connected);
  }
}

class _TimingOutConnection extends DeviceConnection {
  _TimingOutConnection(super.device, super.transport);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  @override
  Future<int> performRetrieveBatteryLevel() async => -1;

  @override
  Future<List<int>> performGetButtonState() async => const [];
}
