import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/connectors/omiglass_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// In-memory transport: `connect()` flips to connected, `disconnect()` to
/// disconnected, and every step is recorded so a test can prove one device's
/// lifecycle never touched another's.
class _FakeTransport extends DeviceTransport {
  _FakeTransport(this._deviceId);

  final String _deviceId;
  final _states = StreamController<DeviceTransportState>.broadcast();
  bool connected = false;
  int connectCalls = 0;
  int disconnectCalls = 0;
  int disposeCalls = 0;

  @override
  String get deviceId => _deviceId;

  @override
  Future<void> connect() async {
    connectCalls++;
    connected = true;
    _states.add(DeviceTransportState.connected);
  }

  @override
  Future<void> disconnect() async {
    disconnectCalls++;
    connected = false;
    _states.add(DeviceTransportState.disconnected);
  }

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<bool> ping() async => connected;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => _states.stream;

  @override
  Future<void> dispose() async {
    disposeCalls++;
  }
}

BtDevice _device(String id, {DeviceType type = DeviceType.omi, String? name}) => BtDevice(
      id: id,
      name: name ?? (type == DeviceType.openglass ? 'OmiGlass' : 'Omi'),
      type: type,
      rssi: -50,
      locator: DeviceLocator.bluetooth(deviceId: id),
    );

void main() {
  late Map<String, _FakeTransport> transports;
  late DeviceService service;
  late List<(String, DeviceConnectionState)> stateEvents;

  DeviceConnection? factory(BtDevice device) {
    final transport = transports.putIfAbsent(device.id, () => _FakeTransport(device.id));
    return device.type == DeviceType.openglass
        ? OmiGlassConnection(device, transport)
        : OmiDeviceConnection(device, transport);
  }

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    transports = {};
    stateEvents = [];
    service = DeviceService(connectionFactory: factory);
    service.start();
    service.subscribe(_RecordingSubscription(stateEvents), stateEvents);
  });

  test('connecting a second device keeps the first one connected', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    SharedPreferencesUtil().companionBtDevice = _device('glass-1', type: DeviceType.openglass);

    final omi = await service.ensureConnection('omi-1', force: true);
    final glass = await service.ensureConnection('glass-1', force: true);

    expect(omi, isA<OmiDeviceConnection>());
    expect(glass, isA<OmiGlassConnection>());
    expect(omi!.status, DeviceConnectionState.connected);
    expect(glass!.status, DeviceConnectionState.connected);
    expect(transports['omi-1']!.disconnectCalls, 0, reason: 'the pendant must survive the glasses connecting');
    expect(transports['omi-1']!.disposeCalls, 0);
    expect(service.connectedConnections.map((c) => c.device.id), containsAll(['omi-1', 'glass-1']));
    expect(service.connectionFor('omi-1'), same(omi));
    expect(service.connectionFor('glass-1'), same(glass));
  });

  test('a non-forced ensureConnection returns the live connection for each device', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    SharedPreferencesUtil().companionBtDevice = _device('glass-1', type: DeviceType.openglass);
    await service.ensureConnection('omi-1', force: true);
    await service.ensureConnection('glass-1', force: true);

    expect((await service.ensureConnection('omi-1'))?.device.id, 'omi-1');
    expect((await service.ensureConnection('glass-1'))?.device.id, 'glass-1');
    expect(await service.ensureConnection('unknown'), isNull);
    expect(transports['omi-1']!.connectCalls, 1);
    expect(transports['glass-1']!.connectCalls, 1);
  });

  test('forgetting one device disposes only that connection', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    SharedPreferencesUtil().companionBtDevice = _device('glass-1', type: DeviceType.openglass);
    await service.ensureConnection('omi-1', force: true);
    await service.ensureConnection('glass-1', force: true);

    await service.forgetDevice('glass-1');

    expect(transports['glass-1']!.disconnectCalls, 1);
    expect(transports['glass-1']!.disposeCalls, 1);
    expect(transports['omi-1']!.disconnectCalls, 0);
    expect(service.connectionFor('glass-1'), isNull);
    expect(service.connectionFor('omi-1')?.status, DeviceConnectionState.connected);
    expect(stateEvents, contains(('glass-1', DeviceConnectionState.disconnected)));
    expect(stateEvents, isNot(contains(('omi-1', DeviceConnectionState.disconnected))));
  });

  test('forcing a reconnect after a BLE drop replaces only that device\'s transport', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    SharedPreferencesUtil().companionBtDevice = _device('glass-1', type: DeviceType.openglass);
    await service.ensureConnection('omi-1', force: true);
    await service.ensureConnection('glass-1', force: true);
    final firstOmiTransport = transports.remove('omi-1')!;

    // Link drop reported by the transport (not a manual disconnect).
    await firstOmiTransport.disconnect();
    await Future<void>.delayed(Duration.zero);
    expect(service.connectionFor('omi-1')?.status, DeviceConnectionState.disconnected);
    expect(stateEvents, contains(('omi-1', DeviceConnectionState.disconnected)));

    final reconnected = await service.ensureConnection('omi-1', force: true);

    expect(firstOmiTransport.disposeCalls, 1, reason: 'the stale transport is released');
    expect(reconnected?.status, DeviceConnectionState.connected);
    expect(transports['omi-1']!.connectCalls, 1, reason: 'a fresh transport carries the reconnect');
    expect(transports['glass-1']!.disconnectCalls, 0);
    expect(transports['glass-1']!.disposeCalls, 0);
    expect(service.connectedConnections, hasLength(2));
  });

  test('a forced ensureConnection on a live device returns it untouched', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    final first = await service.ensureConnection('omi-1', force: true);

    final again = await service.ensureConnection('omi-1', force: true);

    expect(again, same(first));
    expect(transports['omi-1']!.connectCalls, 1);
    expect(transports['omi-1']!.disposeCalls, 0);
  });

  test('a saved companion device reconnects without a scan, like the primary', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    SharedPreferencesUtil().companionBtDevice = _device('glass-1', type: DeviceType.openglass);

    expect(service.devices, isEmpty, reason: 'nothing was discovered');
    final glass = await service.ensureConnection('glass-1', force: true);

    expect(glass, isNotNull);
    expect(glass!.device.type, DeviceType.openglass);
  });

  test('disconnectDevice keeps the connection tracked for a later forced reconnect', () async {
    SharedPreferencesUtil().btDevice = _device('omi-1');
    await service.ensureConnection('omi-1', force: true);

    await service.disconnectDevice('omi-1');
    expect(service.connectionFor('omi-1')?.status, DeviceConnectionState.disconnected);
    expect(await service.ensureConnection('omi-1'), isNull, reason: 'non-forced calls do not reconnect');

    final firstTransport = transports.remove('omi-1')!;
    final reconnected = await service.ensureConnection('omi-1', force: true);
    expect(reconnected?.status, DeviceConnectionState.connected);
    expect(firstTransport.disposeCalls, 1);
  });
}

class _RecordingSubscription implements IDeviceServiceSubsciption {
  _RecordingSubscription(this.events);

  final List<(String, DeviceConnectionState)> events;

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    events.add((deviceId, state));
  }

  @override
  void onDevices(List<BtDevice> devices) {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}
}
