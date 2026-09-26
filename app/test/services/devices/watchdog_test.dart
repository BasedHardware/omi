import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
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
  int connectCalls = 0;

  @override
  DeviceConnectionState get status => _state;

  @override
  Future<void> connect({void Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    connectCalls++;
    _state = DeviceConnectionState.connected;
  }

  @override
  Future<void> disconnect() async {
    _state = DeviceConnectionState.disconnected;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Records every notification so tests can tell discovery (`onDevices` beyond
/// the subscribe() retention call) from silent ticks.
class _RecordingSubscription implements IDeviceServiceSubsciption {
  final deviceBatches = <List<BtDevice>>[];

  @override
  void onDevices(List<BtDevice> devices) => deviceBatches.add(devices);

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {}
}

BtDevice _device(String id) =>
    BtDevice(id: id, name: id, type: DeviceType.omi, rssi: 0, locator: DeviceLocator.bluetooth(deviceId: id));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const liveId = 'AA:BB:CC:DD:EE:01';
  const droppedId = 'AA:BB:CC:DD:EE:02';

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().btDeviceAdd(_device(liveId));
    await SharedPreferencesUtil().btDeviceAdd(_device(droppedId));
  });

  test('watchdog reconnects only stored devices without a live connection', () {
    fakeAsync((async) {
      final built = <String, _FakeConnection>{};
      final service = DeviceService(connectionBuilder: (device) {
        final connection = _FakeConnection(device);
        built[device.id] = connection;
        return connection;
      });
      final subscription = _RecordingSubscription();
      service.subscribe(subscription, #watchdog);

      // One stored device is already connected before the first tick.
      service.ensureConnection(liveId, force: true);
      async.flushMicrotasks();
      expect(service.connectionFor(liveId)?.status, DeviceConnectionState.connected);

      service.start();
      async.elapse(const Duration(seconds: 15));
      async.flushMicrotasks();

      // The stored device with no connection got a reconnect attempt...
      expect(built.containsKey(droppedId), isTrue, reason: 'a stored device with no connection should be reconnected');
      expect(service.connectionFor(droppedId)?.status, DeviceConnectionState.connected);
      // ...and the already-connected one was left alone.
      expect(built[liveId]!.connectCalls, 1, reason: 'a live connection must not be reconnected');
      // With a device connected, the tick must not fall through to discovery.
      expect(subscription.deviceBatches, hasLength(1),
          reason: 'only the subscribe() retention callback — discovery must not run');
    });
  });

  test('watchdog makes no attempts while stale bond recovery is required', () {
    fakeAsync((async) {
      final built = <String, _FakeConnection>{};
      final service = DeviceService(connectionBuilder: (device) {
        final connection = _FakeConnection(device);
        built[device.id] = connection;
        return connection;
      });
      final subscription = _RecordingSubscription();
      service.subscribe(subscription, #watchdog);

      service.requireStaleBondRecovery();
      service.start();
      async.elapse(const Duration(seconds: 35)); // at least two ticks
      async.flushMicrotasks();

      expect(service.staleBondRecoveryRequired, isTrue);
      expect(built, isEmpty, reason: 'no reconnect attempts while stale bond recovery is required');
      expect(subscription.deviceBatches, hasLength(1), reason: 'no discovery while stale bond recovery is required');
    });
  });

  test('watchdog does not rediscover while a connection is live', () {
    fakeAsync((async) {
      final built = <String, _FakeConnection>{};
      final service = DeviceService(connectionBuilder: (device) {
        final connection = _FakeConnection(device);
        built[device.id] = connection;
        return connection;
      });
      final subscription = _RecordingSubscription();
      service.subscribe(subscription, #watchdog);

      service.ensureConnection(liveId, force: true);
      async.flushMicrotasks();
      service.start();
      async.elapse(const Duration(seconds: 50)); // at least three ticks
      async.flushMicrotasks();

      // The live connection is never torn down and re-attempted...
      expect(built[liveId]!.connectCalls, 1);
      expect(service.connectionFor(liveId)?.status, DeviceConnectionState.connected);
      // ...missing stored devices may still be reconnected (that is the watchdog's job)...
      expect(built.containsKey(droppedId), isTrue);
      // ...but discovery never runs while a connection is live.
      expect(subscription.deviceBatches, hasLength(1), reason: 'discovery must not run while a connection is live');
    });
  });
}
