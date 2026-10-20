import 'dart:async';
import 'dart:convert';
import 'dart:io';

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
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/models.dart';
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
    LimitlessDeviceConnection.realtimeSuppressionPolicy = null;
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
    setHostApiHandler('isPeripheralConnected', (message) async => [true]);
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

  void withLateLimitless(
    void Function(FakeAsync, LimitlessDeviceConnection, NativeBleTransport, List<List<int>>) scenario, {
    bool suppressRealtime = false,
    int transientWriteFailures = 0,
    bool failBeforeReady = false,
    bool waitForDartRetry = false,
  }) {
    if (failBeforeReady) {
      setHostApiHandler('configureSavedReconnect', (_) async => <Object?>[]);
      var first = true;
      setHostApiHandler('manageDevice', (_) async {
        if (first) {
          first = false;
          scheduleMicrotask(() => BleBridge.instance.onPeripheralDisconnected(_deviceId, 'connection_failed'));
        }
        return <Object?>[];
      });
    }
    // Use the production UUIDs, rather than a substitute audio transport.
    LimitlessDeviceConnection.realtimeSuppressionPolicy = () => suppressRealtime;
    final writes = <List<int>>[];
    setHostApiHandler('writeCharacteristic', (message) async {
      final args = message as List<Object?>;
      writes.add((args[3] as Uint8List).toList());
      if (transientWriteFailures-- > 0) return ['gatt_error', 'Transient write failure', null];
      return <Object?>[];
    });
    setHostApiHandler('unsubscribeCharacteristic', (_) async => <Object?>[]);

    fakeAsync((async) {
      final device = BtDevice(
        id: _deviceId,
        name: 'Limitless Pendant',
        type: DeviceType.limitless,
        rssi: -50,
        locator: DeviceLocator.bluetooth(deviceId: _deviceId),
      );
      SharedPreferencesUtil().btDeviceSet(device);
      final transport = NativeBleTransport(_deviceId, requiresBond: true);
      final connection = LimitlessDeviceConnection(device, transport);
      final service = DeviceService(connectionBuilder: (_) => connection, reconnectKilled: () => false);
      if (failBeforeReady) {
        service.reconnectSavedDevice('launch');
        async.flushMicrotasks();
      } else {
        service.ensureConnection(device.id, force: true);
        async.elapse(const Duration(seconds: 60));
      }
      expect(service.connectionFor(device.id), same(connection));
      expect(unmanagedCalls, 0);
      if (waitForDartRetry) async.elapse(const Duration(seconds: 5));

      BleBridge.instance.onDeviceReady(_deviceId, [
        BleService(uuid: limitlessServiceUuid, characteristicUuids: [limitlessRxCharUuid, limitlessTxCharUuid]),
      ]);
      async.flushMicrotasks();
      expect(connection.status, DeviceConnectionState.connected);
      scenario(async, connection, transport, writes);

      service.savedReconnect.stop();
      connection.disconnect();
      async.flushMicrotasks();
      transport.dispose();
      async.flushMicrotasks();
      expect(async.nonPeriodicTimerCount, 0);
    });
    LimitlessDeviceConnection.realtimeSuppressionPolicy = null;
  }

  void emitAudioFixture() {
    final fixture =
        jsonDecode(File('test/fixtures/limitless_golden/single_fragment_audio_page.json').readAsStringSync())
            as Map<String, dynamic>;
    for (final hex in fixture['packets'] as List<dynamic>) {
      final value = hex as String;
      final bytes = Uint8List.fromList([
        for (var i = 0; i < value.length; i += 2) int.parse(value.substring(i, i + 2), radix: 16),
      ]);
      BleBridge.instance.onCharacteristicValueUpdated(_deviceId, limitlessServiceUuid, limitlessRxCharUuid, bytes);
    }
  }

  test('late Limitless ready initializes realtime commands and delivers decoded audio after launch timeout', () {
    withLateLimitless((async, connection, transport, writes) {
      final frames = <List<int>>[];
      StreamSubscription? subscription;
      connection.getBleAudioBytesListener(onAudioBytesReceived: frames.add).then((value) => subscription = value);
      async.flushMicrotasks();
      expect(subscription, isNotNull, reason: 'capture must be able to subscribe before setup completes');
      async.elapse(const Duration(seconds: 5));
      expect(writes, hasLength(2), reason: 'late readiness must sync the clock and enable the pendant audio stream');
      expect(subscribedCharacteristics, contains('$limitlessServiceUuid:$limitlessRxCharUuid'));
      emitAudioFixture();
      async.flushMicrotasks();
      expect(frames, hasLength(8));
    });
  });

  test('Limitless native failure before first ready still initializes and delivers audio', () {
    withLateLimitless((async, connection, transport, writes) {
      final frames = <List<int>>[];
      connection.getBleAudioBytesListener(onAudioBytesReceived: frames.add);
      async.elapse(const Duration(seconds: 5));
      expect(writes, hasLength(2), reason: 'late native recovery must run first clock sync and stream enable');
      emitAudioFixture();
      async.flushMicrotasks();
      expect(frames, hasLength(8));
    }, failBeforeReady: true);
  });

  test('Limitless readiness during a Dart backoff attempt initializes only once', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(seconds: 5));
      expect(writes, hasLength(2), reason: 'native listener and pending Dart connect must share first-ready setup');
    }, failBeforeReady: true, waitForDartRetry: true);
  });

  test('late Limitless ready preserves Transcribe Later instead of enabling realtime', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(seconds: 5));
      expect(writes, hasLength(1), reason: 'only clock sync is allowed while realtime is suppressed');
    }, suppressRealtime: true);
  });

  test('disconnect before late Limitless setup prevents subscriptions and network reactivation', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(milliseconds: 500));
      connection.disconnect();
      async.flushMicrotasks();
      connection.onNetworkSocketReconnected();
      async.elapse(const Duration(seconds: 10));
      expect(writes, isEmpty);
      expect(subscribedCharacteristics, isEmpty);
    });
  });

  test('disconnect after late Limitless clock sync cannot enable audio on the released session', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(milliseconds: 2100));
      expect(writes, hasLength(1));
      connection.disconnect();
      async.flushMicrotasks();
      async.elapse(const Duration(seconds: 10));
      expect(writes, hasLength(1));
    });
  });

  test('late Limitless setup retries a transient control failure once and delivers audio', () {
    withLateLimitless((async, connection, transport, writes) {
      final frames = <List<int>>[];
      connection.getBleAudioBytesListener(onAudioBytesReceived: frames.add);
      async.elapse(const Duration(seconds: 8));
      expect(writes, hasLength(3), reason: 'failed clock write, successful clock write, then stream activation');
      emitAudioFixture();
      async.flushMicrotasks();
      expect(frames, hasLength(8));
    }, transientWriteFailures: 1);
  });

  test('late Limitless setup bounds persistent control failures without an endless retry', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(minutes: 1));
      expect(writes, hasLength(2));
    }, transientWriteFailures: 10);
  });

  test('Transcribe Later selected during initial activation wins before setup completes', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(milliseconds: 3100));
      expect(writes, hasLength(2));
      connection.setRealtimeAudioSuppressed(true);
      async.elapse(const Duration(seconds: 2));
      expect(writes, hasLength(3), reason: 'setup must explicitly undo the in-flight realtime enable');
      expect(writes.last, containsAllInOrder([0x42, 0x04, 0x08, 0x00, 0x10, 0x00]));
    });
  });

  test('a second native reconnect replaces pending Limitless setup without enabling the old epoch', () {
    withLateLimitless((async, connection, transport, writes) {
      final frames = <List<int>>[];
      connection.getBleAudioBytesListener(onAudioBytesReceived: frames.add);
      async.elapse(const Duration(milliseconds: 2100));
      expect(writes, hasLength(1));
      BleBridge.instance.onPeripheralDisconnected(_deviceId, null);
      async.flushMicrotasks();
      BleBridge.instance.onDeviceReady(_deviceId, [
        BleService(uuid: limitlessServiceUuid, characteristicUuids: [limitlessRxCharUuid, limitlessTxCharUuid]),
      ]);
      async.elapse(const Duration(seconds: 5));
      expect(writes, hasLength(3), reason: 'old clock write, replacement clock write, replacement activation');
      emitAudioFixture();
      async.flushMicrotasks();
      expect(frames, hasLength(8));
    });
  });

  test('network and mode callbacks cannot reactivate a retired initialized Limitless connection', () {
    withLateLimitless((async, connection, transport, writes) {
      async.elapse(const Duration(seconds: 5));
      expect(writes, hasLength(2));
      connection.onNetworkSocketReconnected();
      async.flushMicrotasks();
      expect(writes, hasLength(3));
      connection.disconnect();
      async.flushMicrotasks();
      connection.setRealtimeAudioSuppressed(false);
      connection.onNetworkSocketReconnected();
      async.elapse(const Duration(seconds: 10));
      expect(writes, hasLength(3),
          reason: 'neither the delayed reconnect nor later settings callbacks may enable audio');
    });
  });
}
