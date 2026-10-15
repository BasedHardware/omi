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
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/friend_pendant_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

const _deviceId = 'omi-pendant-reconnect-test';
const _serviceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
const _charUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final hostApiChannelNames = <String>{};
  final subscribedCharacteristics = <String>[];
  var unmanagedCalls = 0;

  void setHostApiHandler(String methodName, Future<Object?> Function(Object? message) handler) {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final channelName = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$methodName';
    hostApiChannelNames.add(channelName);
    messenger.setMockMessageHandler(channelName, (ByteData? message) async {
      final decoded = BleHostApi.pigeonChannelCodec.decodeMessage(message);
      final response = await handler(decoded);
      return BleHostApi.pigeonChannelCodec.encodeMessage(response);
    });
  }

  tearDown(() {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    for (final channelName in hostApiChannelNames) {
      messenger.setMockMessageHandler(channelName, null);
    }
    hostApiChannelNames.clear();
    BleBridge.instance.clearPeripheralForTesting(_deviceId);
  });

  setUp(() async {
    subscribedCharacteristics.clear();
    unmanagedCalls = 0;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    setHostApiHandler('getBluetoothState', (message) async => ['on']);
    setHostApiHandler('manageDevice', (message) async => <Object?>[]);
    setHostApiHandler('unmanageDevice', (message) async {
      unmanagedCalls++;
      return <Object?>[];
    });
    setHostApiHandler('isPeripheralConnected', (message) async => true);
    setHostApiHandler('subscribeCharacteristic', (message) async {
      final args = message as List<Object?>;
      subscribedCharacteristics.add('${args[1]}:${args[2]}');
      return <Object?>[];
    });
  });

  test('saved pendant out of range at launch maintains BleBridge registration and reconnects on device ready', () {
    fakeAsync((async) {
      final device = BtDevice(
        id: _deviceId,
        name: 'Omi Pendant',
        type: DeviceType.omi,
        rssi: -50,
        locator: DeviceLocator.bluetooth(deviceId: _deviceId),
      );
      SharedPreferencesUtil().btDeviceSet(device);

      final transport = NativeBleTransport(_deviceId);
      final connection = FriendPendantDeviceConnection(device, transport);
      final service = DeviceService(connectionBuilder: (_) => connection);

      // Launch connection attempt starts
      var connectionDone = false;
      DeviceConnection? connectionResult;
      service.ensureConnection(device.id, force: true).then((res) {
        connectionDone = true;
        connectionResult = res;
      });

      // Elapse 60 seconds to simulate timeout
      async.elapse(const Duration(seconds: 60));
      expect(connectionDone, isTrue);
      expect(connectionResult, isNull);

      // Verify transport is NOT unmanaged and remains registered in service
      expect(unmanagedCalls, 0);
      expect(service.connectionFor(device.id), same(connection));
      expect(connection.status, DeviceConnectionState.disconnected);

      // Now the pendant comes back into range: native emits onDeviceReady
      final services = [
        BleService(uuid: _serviceUuid, characteristicUuids: [_charUuid]),
      ];
      BleBridge.instance.onDeviceReady(_deviceId, services);
      async.flushMicrotasks();

      // Transport & connection transition to connected
      expect(connection.status, DeviceConnectionState.connected);
    });
  });
}
