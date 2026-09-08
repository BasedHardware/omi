import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _FakeTransport implements DeviceTransport {
  _FakeTransport(this.deviceId);

  @override
  final String deviceId;
  bool disposed = false;

  @override
  Future<void> dispose() async => disposed = true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeConnection implements DeviceConnection {
  _FakeConnection(this.device) : transport = _FakeTransport(device.id);

  @override
  final BtDevice device;
  @override
  final _FakeTransport transport;

  DeviceConnectionState _state = DeviceConnectionState.disconnected;
  bool disconnectCalled = false;

  @override
  DeviceConnectionState get status => _state;

  @override
  Future<void> connect({void Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    _state = DeviceConnectionState.connected;
  }

  @override
  Future<void> disconnect() async {
    disconnectCalled = true;
    _state = DeviceConnectionState.disconnected;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

BtDevice _device(String id, {DeviceType type = DeviceType.omi}) =>
    BtDevice(id: id, name: id, type: type, rssi: 0, locator: DeviceLocator.bluetooth(deviceId: id));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const audioId = 'AA:BB:CC:DD:EE:FF';
  const glassId = '11:22:33:44:55:66';

  late Map<String, _FakeConnection> built;
  late DeviceService service;

  final mockedChannels = <String>{};

  void mockBleHostApi(String method) {
    final channel = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
    mockedChannels.add(channel);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      channel,
      (ByteData? message) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[null]),
    );
  }

  tearDown(() {
    for (final channel in mockedChannels) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(channel, null);
    }
    mockedChannels.clear();
  });

  setUp(() async {
    mockBleHostApi('stopScan');
    mockBleHostApi('startScan');
    final audio = _device(audioId);
    final glass = _device(glassId, type: DeviceType.openglass);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().btDeviceAdd(audio);
    await SharedPreferencesUtil().btDeviceAdd(glass);

    built = {};
    service = DeviceService(connectionBuilder: (device) {
      final connection = _FakeConnection(device);
      built[device.id] = connection;
      return connection;
    });
  });

  test('connecting a second device leaves the first connected', () async {
    await service.ensureConnection(audioId, force: true);
    await service.ensureConnection(glassId, force: true);

    expect(service.connectionFor(audioId)?.status, DeviceConnectionState.connected);
    expect(service.connectionFor(glassId)?.status, DeviceConnectionState.connected);
    expect(built[audioId]!.disconnectCalled, isFalse);
    expect(built[audioId]!.transport.disposed, isFalse);
    expect(service.connections.length, 2);
  });

  test('an already connected device is reused rather than reconnected', () async {
    final first = await service.ensureConnection(audioId, force: true);
    final second = await service.ensureConnection(audioId, force: true);

    expect(identical(first, second), isTrue);
    expect(service.connections.length, 1);
  });

  test('disconnecting one device leaves the other alone', () async {
    await service.ensureConnection(audioId, force: true);
    await service.ensureConnection(glassId, force: true);

    await service.disconnectDevice(audioId);

    expect(service.connectionFor(audioId), isNull);
    expect(service.connectionFor(glassId)?.status, DeviceConnectionState.connected);
    expect(built[glassId]!.disconnectCalled, isFalse);
  });

  test('forgetting one device does not tear down another', () async {
    await service.ensureConnection(audioId, force: true);
    await service.ensureConnection(glassId, force: true);

    await service.forgetDevice(audioId);

    expect(service.connectionFor(audioId), isNull);
    expect(built[audioId]!.transport.disposed, isTrue);
    expect(service.connectionFor(glassId)?.status, DeviceConnectionState.connected);
    expect(built[glassId]!.transport.disposed, isFalse);
  });

  test('stopping the service tears down every connection', () async {
    await service.ensureConnection(audioId, force: true);
    await service.ensureConnection(glassId, force: true);

    await service.stop();

    expect(service.connections, isEmpty);
    expect(built[audioId]!.transport.disposed, isTrue);
    expect(built[glassId]!.transport.disposed, isTrue);
  });

  test('without force a device that has never connected is not connected', () async {
    final connection = await service.ensureConnection(audioId);

    expect(connection, isNull);
    expect(service.connections, isEmpty);
  });
}
