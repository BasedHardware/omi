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
}
