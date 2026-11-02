import 'dart:async';
import 'package:fake_async/fake_async.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/friend_pendant_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

const a = 'saved-pendant-a';
const b = 'saved-pendant-b';
BtDevice pendant(String id) =>
    BtDevice(id: id, name: 'Omi', type: DeviceType.omi, rssi: -50, locator: DeviceLocator.bluetooth(deviceId: id));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final channels = <String>[];
  final calls = <String>[];
  final live = <String>{};
  final nativeSavedIntent = <String>{};
  final owners = <DeviceService>[];
  void handle(String method, Object? Function(List<Object?>) body) {
    final name = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
    channels.add(name);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(name, (message) async {
      final args = BleHostApi.pigeonChannelCodec.decodeMessage(message) as List<Object?>? ?? [];
      try {
        return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[body(args)]);
      } on PlatformException catch (error) {
        return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[error.code, error.message, error.details]);
      }
    });
  }

  DeviceService service({bool kill = false, Completer<bool>? refresh}) {
    final owner = DeviceService(
      reconnectKilled: () => kill,
      refreshReconnectKilled: refresh == null ? () async => kill : () => refresh.future,
      connectionBuilder: (device) => FriendPendantDeviceConnection(device, NativeBleTransport(device.id)),
    );
    owners.add(owner);
    return owner;
  }

  setUp(() async {
    calls.clear();
    live.clear();
    nativeSavedIntent.clear();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    handle('getBluetoothState', (_) => 'on');
    handle('stopScan', (_) => null);
    handle('configureSavedReconnect', (args) {
      calls.add('config:${args[0]}:${args[1]}');
      args[1] == true ? nativeSavedIntent.add(args[0] as String) : nativeSavedIntent.remove(args[0]);
      return null;
    });
    handle('manageDevice', (args) {
      final id = args[0] as String;
      calls.add('manage:$id');
      live.add(id);
      scheduleMicrotask(() => BleBridge.instance.onDeviceReady(id, []));
      return null;
    });
    handle('unmanageDevice', (args) {
      calls.add('unmanage:${args[0]}');
      live.remove(args[0]);
      return null;
    });
    handle('isPeripheralConnected', (args) => live.contains(args[0]));
    handle('readCharacteristic', (_) => Uint8List(0));
    handle('writeCharacteristic', (_) => null);
  });
  tearDown(() async {
    for (final owner in owners) {
      await owner.stop();
    }
    owners.clear();
    for (final id in [a, b]) {
      BleBridge.instance.clearPeripheralForTesting(id);
    }
    for (final name in channels) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(name, null);
    }
    channels.clear();
  });

  test('DFU internal disconnect then process restart reconnects without a persisted user block', () async {
    await SharedPreferencesUtil().btDeviceSet(pendant(a));
    final first = service();
    await first.reconnectSavedDevice('launch');
    first.reconnectPaused = true;
    calls.clear();
    await first.disconnectDevice(a);
    expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
    expect(nativeSavedIntent, isEmpty);
    expect(SharedPreferencesUtil().getStringList('manualBleDisconnects'), isEmpty);
    await first.stop();
    final relaunched = service();
    await relaunched.reconnectSavedDevice('launch');
    expect(relaunched.connectionFor(a)?.status, DeviceConnectionState.connected);
    expect(calls.where((value) => value == 'manage:$a'), hasLength(1), reason: 'calls were reset before DFU teardown');
    relaunched.savedReconnect.stop();
  });

  for (final continueEpisode in [true, false]) {
    test('capture-wedge recovery keeps reconnect intent when follow-up is $continueEpisode', () async {
      await SharedPreferencesUtil().btDeviceSet(pendant(a));
      final owner = service();
      await owner.reconnectSavedDevice('launch');
      calls.clear();
      await owner.recoverConnection(a, shouldRetry: () => continueEpisode);
      expect(nativeSavedIntent, contains(a), reason: 'native owns reconnect even without a Dart follow-up');
      expect(calls, isNot(contains('config:$a:false')));
      expect(SharedPreferencesUtil().getStringList('manualBleDisconnects'), isEmpty);
      if (!continueEpisode) await owner.reconnectSavedDevice('resume');
      expect(owner.connectionFor(a)?.status, DeviceConnectionState.connected);
      owner.savedReconnect.stop();
    });
  }

  test('stop retires a native recovery owner after its Dart transport was released', () async {
    await SharedPreferencesUtil().btDeviceSet(pendant(a));
    final owner = service();
    await owner.reconnectSavedDevice('launch');
    await owner.recoverConnection(a, shouldRetry: () => false);
    expect(owner.connectionFor(a), isNull);
    expect(nativeSavedIntent, contains(a));
    calls.clear();
    await owner.stop();
    expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
    expect(nativeSavedIntent, isEmpty);
  });

  test('manual disconnect disarms native intent before transport teardown', () async {
    await SharedPreferencesUtil().btDeviceSet(pendant(a));
    final owner = service();
    await owner.reconnectSavedDevice('launch');
    calls.clear();
    await owner.disconnectDevice(a, userInitiated: true);
    expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
    expect(nativeSavedIntent, isNot(contains(a)));
    await owner.reconnectSavedDevice('resume');
    expect(calls, isNot(contains('manage:$a')));
  });

  for (final hasTransport in [true, false]) {
    test('manual disconnect still tears down when native disarm fails; transport=$hasTransport', () async {
      await SharedPreferencesUtil().btDeviceSet(pendant(a));
      final owner = service();
      await owner.reconnectSavedDevice('launch');
      if (!hasTransport) await owner.recoverConnection(a, shouldRetry: () => false);
      calls.clear();
      handle('configureSavedReconnect', (args) {
        calls.add('config:${args[0]}:${args[1]}');
        throw PlatformException(code: 'temporarily_unavailable');
      });
      await owner.disconnectDevice(a, userInitiated: true);
      expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
      expect(owner.connectionFor(a), isNull);
      expect(live, isNot(contains(a)));
      expect(SharedPreferencesUtil().getStringList('manualBleDisconnects'), contains(a));
      await owner.reconnectSavedDevice('resume');
      expect(calls, isNot(contains('manage:$a')));
      // Failed disarm stays tracked so service shutdown can retry it.
      handle('configureSavedReconnect', (args) {
        calls.add('retry:${args[0]}:${args[1]}');
        return null;
      });
      await owner.stop();
      expect(calls, contains('retry:$a:false'));
    });
  }

  test('forget and service stop retire native ownership before teardown', () async {
    await SharedPreferencesUtil().btDeviceSet(pendant(a));
    final owner = service();
    await owner.reconnectSavedDevice('launch');
    calls.clear();
    await owner.forgetDevice(a);
    expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
    expect(nativeSavedIntent, isEmpty);
    await owner.ensureConnection(a, force: true);
    await owner.reconnectSavedDevice('resume');
    calls.clear();
    await owner.stop();
    expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
    expect(nativeSavedIntent, isEmpty);
  });

  test('kill mode ignores new manual flag and never writes new suppression', () {
    fakeAsync((async) {
      SharedPreferencesUtil().btDeviceSet(pendant(a));
      SharedPreferencesUtil().saveStringList('manualBleDisconnects', [a]);
      final owner = service(kill: true);
      owner.reconnectSavedDevice('launch');
      async.flushMicrotasks();
      expect(owner.connectionFor(a)?.status, DeviceConnectionState.connected);
      expect(calls, isNot(contains('config:$a:true')));
      owner.disconnectDevice(a, userInitiated: true);
      async.flushMicrotasks();
      owner.forgetDevice(b);
      async.flushMicrotasks();
      expect(SharedPreferencesUtil().getStringList('manualBleDisconnects'), [a]);
      owner.savedReconnect.stop();
    });
  });

  for (final toBluetooth in [true, false]) {
    test('saved target changes retire old native owner before ${toBluetooth ? 'new pendant' : 'Meta input'}', () async {
      await SharedPreferencesUtil().btDeviceSet(pendant(a));
      final owner = service();
      await owner.reconnectSavedDevice('launch');
      calls.clear();
      await SharedPreferencesUtil()
          .btDeviceSet(toBluetooth ? pendant(b) : BtDevice(id: b, name: 'Meta', type: DeviceType.raybanMeta, rssi: 0));
      await owner.reconnectSavedDevice('launch');
      await pumpEventQueue(); // Wait for the observed target-change attempt already in flight.
      expect(owner.connectionFor(a), isNull);
      expect(live.contains(a), isFalse);
      expect(calls, containsAllInOrder(['config:$a:false', 'unmanage:$a']));
      if (toBluetooth) {
        expect(calls, containsAllInOrder(['unmanage:$a', 'manage:$b']));
        expect(owner.connectionFor(b)?.status, DeviceConnectionState.connected);
      }
      BleBridge.instance.onBluetoothStateChanged('on');
      await pumpEventQueue();
      expect(calls, isNot(contains('manage:$a')));
      owner.savedReconnect.stop();
    });
  }

  test('a failed old-target disarm is retried before managing the replacement', () async {
    await SharedPreferencesUtil().btDeviceSet(pendant(a));
    final owner = service();
    await owner.reconnectSavedDevice('launch');
    var fail = true;
    handle('configureSavedReconnect', (args) {
      calls.add('config:${args[0]}:${args[1]}');
      if (args[0] == a && args[1] == false && fail) {
        fail = false;
        throw PlatformException(code: 'temporarily_unavailable');
      }
      return null;
    });
    await SharedPreferencesUtil().btDeviceSet(pendant(b));
    await pumpEventQueue();
    expect(calls, isNot(contains('manage:$b')));
    await owner.reconnectSavedDevice('resume');
    await pumpEventQueue();
    expect(calls, containsAllInOrder(['unmanage:$a', 'manage:$b']));
    expect(owner.connectionFor(b)?.status, DeviceConnectionState.connected);
    owner.savedReconnect.stop();
  });

  test('switching away from a pending native attempt cancels it before managing the replacement', () async {
    handle('manageDevice', (args) {
      final id = args[0] as String;
      calls.add('manage:$id');
      if (id == b) {
        live.add(id);
        scheduleMicrotask(() => BleBridge.instance.onDeviceReady(id, []));
      }
      return null;
    });
    await SharedPreferencesUtil().btDeviceSet(pendant(a));
    final owner = service();
    final firstAttempt = owner.reconnectSavedDevice('launch');
    await pumpEventQueue();
    expect(calls, contains('manage:$a'));
    await SharedPreferencesUtil().btDeviceSet(pendant(b));
    await owner.reconnectSavedDevice('launch');
    await firstAttempt;
    await pumpEventQueue();
    expect(calls, containsAllInOrder(['unmanage:$a', 'manage:$b']));
    expect(owner.connectionFor(a), isNull);
    expect(owner.connectionFor(b)?.status, DeviceConnectionState.connected);
    owner.savedReconnect.stop();
  });

  test('real service launch is immediate while flag refresh hangs; late kill disarms it', () {
    fakeAsync((async) {
      SharedPreferencesUtil().btDeviceSet(pendant(a));
      final flag = Completer<bool>();
      final owner = service(refresh: flag);
      owner.reconnectSavedDevice('launch');
      async.flushMicrotasks();
      expect(owner.connectionFor(a)?.status, DeviceConnectionState.connected);
      expect(calls, contains('manage:$a'));
      flag.complete(true);
      async.flushMicrotasks();
      expect(calls, contains('config:$a:false'));
      owner.savedReconnect.stop();
    });
  });
}
