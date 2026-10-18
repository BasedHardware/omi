import 'dart:async';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/native_link_reconciler.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/logger.dart';

// A native link that is up while Dart shows "Disconnected" until the app is
// killed: the launch connect gave up at its 60s deadline, the pendant arrived
// later, and nothing in Dart adopted the late device-ready.

const _deviceId = 'B56E190F-1298-F479-A89D-21C3B506DEA5';
final _services = [
  BleService(
      uuid: '19b10000-e8f2-537e-4f6c-d104768a1214', characteristicUuids: ['19b10001-e8f2-537e-4f6c-d104768a1214']),
];

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final channels = <String>{};
  var linkUp = false;
  var adapterState = 'on';
  var failNativeOnce = false;
  var nativeReplaysReady = false;
  var manageCalls = 0;
  var unmanageCalls = 0;
  var unmanageFails = false;

  void handle(String method, Object? Function(List<Object?> args) reply) {
    final name = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
    channels.add(name);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(name, (message) async {
      final args = (BleHostApi.pigeonChannelCodec.decodeMessage(message) as List<Object?>?) ?? const [];
      return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[reply(args)]);
    });
  }

  void pairPendant() => SharedPreferencesUtil().btDeviceSet(BtDevice(
        id: _deviceId,
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: _deviceId),
      ));

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {}
  });

  setUp(() {
    linkUp = false;
    adapterState = 'on';
    failNativeOnce = false;
    SharedPreferencesUtil().saveStringList('manualBleDisconnects', []);
    nativeReplaysReady = false;
    unmanageFails = false;
    manageCalls = 0;
    unmanageCalls = 0;
    handle('getBluetoothState', (_) => adapterState);
    handle('configureSavedReconnect', (_) => null);
    handle('manageDevice', (args) {
      manageCalls++;
      if (failNativeOnce) {
        failNativeOnce = false;
        scheduleMicrotask(() => BleBridge.instance.onPeripheralDisconnected(_deviceId, 'connection_failed'));
        return null;
      }
      // Native answers manageDevice for an already-connected peripheral by
      // replaying device-ready (iOS replayReady, Android adoptConnectedDevice).
      if (nativeReplaysReady && args.first == _deviceId) {
        scheduleMicrotask(() => BleBridge.instance.onDeviceReady(_deviceId, _services));
      }
      return null;
    });
    handle('unmanageDevice', (_) {
      unmanageCalls++;
      return null;
    });
    const unmanage = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.unmanageDevice';
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(unmanage, (message) async {
      unmanageCalls++;
      // A pigeon error reply: [code, message, details].
      return BleHostApi.pigeonChannelCodec
          .encodeMessage(unmanageFails ? <Object?>['ble', 'native busy', null] : <Object?>[null]);
    });
    handle('isPeripheralConnected', (_) => linkUp);
    handle('subscribeCharacteristic', (_) => null);
    handle('unsubscribeCharacteristic', (_) => null);
    handle('writeCharacteristic', (_) => null);
    handle('readCharacteristic', (_) => Uint8List.fromList([80]));
  });

  tearDown(() async {
    await ServiceManager.instance().device.forgetDevice(_deviceId);
    for (final name in channels) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(name, null);
    }
    channels.clear();
    BleBridge.instance.clearPeripheralForTesting(_deviceId);
  });

  test('a link that becomes ready after the launch connect timed out still reaches the provider', () {
    fakeAsync((async) {
      pairPendant();
      final provider = DeviceProvider();

      provider.initiateConnection('HomePageWrapper', boundDeviceOnly: true);
      async.elapse(const Duration(seconds: 61));
      expect(manageCalls, 1);
      expect(provider.isConnected, isFalse, reason: 'the launch connect gave up at its deadline');

      linkUp = true;
      BleBridge.instance.onDeviceReady(_deviceId, _services);
      async.elapse(const Duration(seconds: 5));

      expect(provider.isConnected, isTrue);
      expect(provider.connectedDevice?.id, _deviceId);
      provider.dispose();
      async.flushTimers();
    });
  });

  test('out of range launch retries the same owner and reconnects without relaunch', () {
    fakeAsync((async) {
      pairPendant();
      final provider = DeviceProvider();
      provider.initiateConnection('HomePageWrapper', boundDeviceOnly: true);
      async.elapse(const Duration(seconds: 61));
      final owner = ServiceManager.instance().device.connectionFor(_deviceId);
      expect(manageCalls, 1);
      async.elapse(const Duration(seconds: 5));
      expect(manageCalls, 2);
      expect(ServiceManager.instance().device.connectionFor(_deviceId), same(owner));
      expect(unmanageCalls, 0);
      linkUp = true;
      BleBridge.instance.onDeviceReady(_deviceId, _services);
      async.elapse(const Duration(seconds: 5));
      expect(provider.isConnected, isTrue);
      async.elapse(const Duration(minutes: 10));
      expect(manageCalls, 2, reason: 'a connected link has no retry timer');
      provider.dispose();
      async.flushMicrotasks();
    });
  });

  test('adapter unknown at launch recovers on adapter_on without losing its owner', () {
    fakeAsync((async) {
      pairPendant();
      adapterState = 'unknown';
      final provider = DeviceProvider();
      provider.initiateConnection('HomePageWrapper', boundDeviceOnly: true);
      async.flushMicrotasks();
      final owner = ServiceManager.instance().device.connectionFor(_deviceId);
      expect(owner, isNotNull);
      expect(manageCalls, 0);
      expect(unmanageCalls, 0);
      adapterState = 'on';
      linkUp = true;
      nativeReplaysReady = true;
      BleBridge.instance.onBluetoothStateChanged('on');
      async.elapse(const Duration(seconds: 5));
      expect(ServiceManager.instance().device.connectionFor(_deviceId), same(owner));
      expect(manageCalls, 1);
      expect(provider.isConnected, isTrue);
      provider.dispose();
      async.flushMicrotasks();
    });
  });

  test('native fail-to-connect at launch recovers on resume using the retained transport', () {
    fakeAsync((async) {
      pairPendant();
      failNativeOnce = true;
      final provider = DeviceProvider();
      provider.initiateConnection('HomePageWrapper', boundDeviceOnly: true);
      async.flushMicrotasks();
      final owner = ServiceManager.instance().device.connectionFor(_deviceId);
      expect(owner, isNotNull);
      expect(unmanageCalls, 0);
      nativeReplaysReady = true;
      linkUp = true;
      TestWidgetsFlutterBinding.instance.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      TestWidgetsFlutterBinding.instance.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      async.elapse(const Duration(seconds: 3));
      expect(manageCalls, 2);
      expect(ServiceManager.instance().device.connectionFor(_deviceId), same(owner));
      expect(provider.isConnected, isTrue);
      provider.dispose();
      async.flushMicrotasks();
    });
  });

  for (final forget in [false, true]) {
    test('${forget ? 'forget' : 'manual disconnect'} cancels retries and fences late ready', () {
      fakeAsync((async) {
        pairPendant();
        final provider = DeviceProvider();
        provider.initiateConnection('HomePageWrapper', boundDeviceOnly: true);
        async.flushMicrotasks();
        final service = ServiceManager.instance().device;
        if (forget) {
          service.forgetDevice(_deviceId);
        } else {
          service.disconnectDevice(_deviceId, userInitiated: true);
        }
        async.flushMicrotasks();
        expect(unmanageCalls, 1);
        BleBridge.instance.onDeviceReady(_deviceId, _services);
        BleBridge.instance.onBluetoothStateChanged('on');
        service.reconnectSavedDevice('resume');
        async.elapse(const Duration(minutes: 15));
        expect(manageCalls, 1);
        expect(provider.isConnected, isFalse);
        expect(service.canAutoReconnectDevice(_deviceId), isFalse);
        provider.dispose();
        async.flushMicrotasks();
      });
    });
  }

  test('a retired registration cannot silence the transport that replaced it', () {
    final readyFor = <String>[];
    final releaseOld = BleBridge.instance.registerPeripheral(
      peripheralUuid: _deviceId,
      onDeviceReady: (_) => readyFor.add('old'),
    );
    final releaseNew = BleBridge.instance.registerPeripheral(
      peripheralUuid: _deviceId,
      onDeviceReady: (_) => readyFor.add('new'),
    );

    releaseOld();
    BleBridge.instance.onDeviceReady(_deviceId, _services);
    expect(readyFor, ['new']);

    releaseNew();
    BleBridge.instance.onDeviceReady(_deviceId, _services);
    expect(readyFor, ['new'], reason: 'the owner releases its own registration');
  });

  test('disconnecting after a timed-out connect releases native and leaves no orphan transport', () {
    fakeAsync((async) {
      pairPendant();
      final service = ServiceManager.instance().device;
      service.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 61));
      final timedOut = service.connectionFor(_deviceId);
      expect(timedOut, isNotNull, reason: 'a launch timeout keeps the transport for native auto-reconnect');
      expect(timedOut!.status, DeviceConnectionState.disconnected);
      final transportStates = <DeviceTransportState>[];
      timedOut.transport.connectionStateStream.listen(transportStates.add);

      service.disconnectDevice(_deviceId, userInitiated: true);
      async.elapse(const Duration(seconds: 1));

      expect(unmanageCalls, 1, reason: 'native was still connecting; an explicit disconnect must stop it');
      expect(service.connectionFor(_deviceId), isNull);

      // A late ready must not land on the retired transport, where no
      // connection listens and the link would be adopted invisibly.
      BleBridge.instance.onDeviceReady(_deviceId, _services);
      async.flushMicrotasks();
      expect(transportStates, isNot(contains(DeviceTransportState.connected)));
    });
  });

  test('disconnectDevice disposes the transport it drops', () async {
    pairPendant();
    linkUp = true;
    nativeReplaysReady = true;
    final service = ServiceManager.instance().device;
    final connection = await service.ensureConnection(_deviceId, force: true);
    expect(connection?.status, DeviceConnectionState.connected);
    var transportClosed = false;
    connection!.transport.connectionStateStream.listen((_) {}, onDone: () => transportClosed = true);

    await service.disconnectDevice(_deviceId, userInitiated: true);
    await pumpEventQueue();

    expect(transportClosed, isTrue, reason: 'an undisposed transport stays registered for native events');
  });

  test('foreground reconcile re-adopts a link native holds while the provider shows disconnected', () {
    fakeAsync((async) {
      pairPendant();
      final provider = DeviceProvider();
      linkUp = true;
      nativeReplaysReady = true;

      provider.nativeLink.reconcile();
      async.elapse(const Duration(seconds: 5));

      expect(manageCalls, 1);
      expect(provider.isConnected, isTrue);
      expect(provider.connectedDevice?.id, _deviceId);
      provider.dispose();
      async.flushTimers();
    });
  });

  test('foreground reconcile never starts a physical connect', () {
    fakeAsync((async) {
      pairPendant();
      final provider = DeviceProvider();

      provider.nativeLink.reconcile();
      async.elapse(const Duration(seconds: 5));

      expect(manageCalls, 0,
          reason: 'native has no link; reconnecting is native auto-reconnect, not a resume side effect');
      expect(provider.isConnected, isFalse);
      provider.dispose();
      async.flushTimers();
    });
  });

  test('foreground reconcile republishes a link DeviceService already holds', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      nativeReplaysReady = true;
      ServiceManager.instance().device.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 5));
      expect(ServiceManager.instance().device.connectionFor(_deviceId)?.status, DeviceConnectionState.connected);

      // A provider that missed the connect event (recreated, or the event was
      // lost) mirrors disconnected over DeviceService's connected link.
      final provider = DeviceProvider();
      expect(provider.isConnected, isFalse);

      provider.nativeLink.reconcile();
      async.elapse(const Duration(seconds: 5));

      expect(provider.isConnected, isTrue);
      expect(manageCalls, 1, reason: 'the held connection is republished, not reconnected');
      provider.dispose();
      async.flushTimers();
    });
  });

  test('a readoption queued behind the connect debounce is dropped when pairing moves on', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      nativeReplaysReady = true;
      ServiceManager.instance().device.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 5));
      expect(ServiceManager.instance().device.connectionFor(_deviceId)?.status, DeviceConnectionState.connected);

      final provider = DeviceProvider();
      expect(provider.isConnected, isFalse);
      final probe = Completer<bool>();
      final reconciler = NativeLinkReconciler(provider, nativeLinkProbe: (_) => probe.future);

      reconciler.reconcile();
      probe.complete(true);
      // Let the probe resolve and queue the readmission behind the 100 ms
      // connect debounce, then move the pairing elsewhere before it fires.
      async.flushMicrotasks();
      expect(provider.isConnected, isFalse, reason: 'admission is still queued');
      SharedPreferencesUtil().btDeviceSet(BtDevice(
        id: 'OTHER-PENDANT',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'OTHER-PENDANT'),
      ));
      async.elapse(const Duration(seconds: 5));

      expect(provider.isConnected, isFalse, reason: 'the old device must not publish over the newer pairing');
      expect(provider.connectedDevice?.id, isNot(_deviceId));
      expect(SharedPreferencesUtil().btDevice.id, 'OTHER-PENDANT',
          reason: 'the stale admission must not rewrite pairing');
      reconciler.dispose();
      provider.dispose();
      async.flushTimers();
    });
  });

  test('foreground reconcile adopts only the device whose link it probed', () {
    fakeAsync((async) {
      pairPendant();
      final provider = DeviceProvider();
      final probe = Completer<bool>();
      final reconciler = NativeLinkReconciler(provider, nativeLinkProbe: (_) => probe.future);

      reconciler.reconcile();
      SharedPreferencesUtil().btDeviceSet(BtDevice(
        id: 'OTHER-PENDANT',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'OTHER-PENDANT'),
      ));
      probe.complete(true);
      async.elapse(const Duration(seconds: 5));

      expect(manageCalls, 0, reason: 'the newly paired device was never probed');
      reconciler.dispose();
      provider.dispose();
      async.flushTimers();
    });
  });

  test('a failed native release stays retryable and keeps adopting native readies', () {
    fakeAsync((async) {
      pairPendant();
      final service = ServiceManager.instance().device;
      service.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 61));
      final connection = service.connectionFor(_deviceId)!;
      final transportStates = <DeviceTransportState>[];
      connection.transport.connectionStateStream.listen(transportStates.add);

      unmanageFails = true;
      connection.transport.disconnect();
      async.elapse(const Duration(seconds: 1));
      expect(unmanageCalls, 1);

      // Native still owns the link, so its ready must not be dropped.
      BleBridge.instance.onDeviceReady(_deviceId, _services);
      async.flushMicrotasks();
      expect(transportStates.last, DeviceTransportState.connected);

      unmanageFails = false;
      connection.transport.disconnect();
      async.elapse(const Duration(seconds: 1));
      expect(unmanageCalls, 2, reason: 'release is retried after a failure');
    });
  });

  test('a ready delivered while a release is pending is replayed when that release fails', () {
    fakeAsync((async) {
      pairPendant();
      final service = ServiceManager.instance().device;
      service.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 61));
      final connection = service.connectionFor(_deviceId)!;
      final transportStates = <DeviceTransportState>[];
      connection.transport.connectionStateStream.listen(transportStates.add);

      // The release hangs; native delivers the ready while it is pending, then
      // the release fails. The buffered ready must be replayed, not dropped.
      final release = Completer<void>();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMessageHandler('dev.flutter.pigeon.omi_pigeon.BleHostApi.unmanageDevice', (message) async {
        unmanageCalls++;
        await release.future;
        return BleHostApi.pigeonChannelCodec
            .encodeMessage(unmanageFails ? <Object?>['ble', 'native busy', null] : <Object?>[null]);
      });
      unmanageFails = true;
      connection.transport.disconnect();
      BleBridge.instance.onDeviceReady(_deviceId, _services);
      release.complete();
      async.flushMicrotasks();

      expect(transportStates.last, DeviceTransportState.connected,
          reason: 'the pending ready survives the failed release and re-adopts the live link');

      // Settle the transport like the failed-release test above so tearDown
      // finds a released, disconnected transport.
      unmanageFails = false;
      connection.transport.disconnect();
      async.elapse(const Duration(seconds: 1));
      expect(unmanageCalls, 2);
    });
  });

  test('a reconcile adopt of a forming connection is dropped when pairing moves on', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      // manageDevice replays ready only for the *held* case; a fresh ensure
      // connection must still complete, driven here by the native replay.
      nativeReplaysReady = true;
      final provider = DeviceProvider();
      final probe = Completer<bool>();
      final reconciler = NativeLinkReconciler(provider, nativeLinkProbe: (_) => probe.future);

      reconciler.reconcile();
      probe.complete(true);
      async.flushMicrotasks();
      // The transport is forming; the persisted pairing moves on before the
      // connected admission can run.
      SharedPreferencesUtil().btDeviceSet(BtDevice(
        id: 'OTHER-PENDANT',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'OTHER-PENDANT'),
      ));
      async.elapse(const Duration(seconds: 5));

      expect(provider.isConnected, isFalse, reason: 'the forming link belongs to a retired pairing');
      expect(SharedPreferencesUtil().btDevice.id, 'OTHER-PENDANT');
      reconciler.dispose();
      provider.dispose();
      async.flushTimers();
    });
  });

  test('overlapping connected events for one physical connect run connect side effects once', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      nativeReplaysReady = true;
      final service = ServiceManager.instance().device;
      service.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 5));

      final provider = DeviceProvider();
      int admissions() =>
          Logger.instance.talker.history.where((e) => '${e.message}'.startsWith('_onConnected inside')).length;
      final admittedBefore = admissions();
      // Connection handling now holds DeviceService's mutex on a slow native
      // link check, so the first connected event is still mid-flight while
      // the provider mirrors disconnected.
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMessageHandler('dev.flutter.pigeon.omi_pigeon.BleHostApi.isPeripheralConnected', (_) async {
        await Future<void>.delayed(const Duration(seconds: 2));
        return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[true]);
      });
      final reconciler = NativeLinkReconciler(provider, nativeLinkProbe: (_) async => true);

      provider.onDeviceConnectionStateChanged(_deviceId, DeviceConnectionState.connected);
      async.elapse(const Duration(milliseconds: 150));
      reconciler.reconcile();
      async.elapse(const Duration(seconds: 15));

      expect(provider.isConnected, isTrue);
      expect(admissions() - admittedBefore, 1);
      reconciler.dispose();
      provider.dispose();
      async.flushTimers();
    });
  });

  test('a generic admission racing a fresh reconcile is dropped when pairing moves on', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      nativeReplaysReady = true;
      final provider = DeviceProvider();
      // DeviceConnection.connect emits connected before awaiting ping and
      // getDeviceInfo, so the transport's own connected event queues the
      // generic admission while the reconcile is still forming the link.
      // Block that admission inside ensureConnection behind DeviceService's
      // mutex on a slow native link check.
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMessageHandler('dev.flutter.pigeon.omi_pigeon.BleHostApi.isPeripheralConnected', (_) async {
        await Future<void>.delayed(const Duration(seconds: 2));
        return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[true]);
      });
      final reconciler = NativeLinkReconciler(provider, nativeLinkProbe: (_) async => true);

      reconciler.reconcile();
      async.elapse(const Duration(milliseconds: 50));
      // The transport's connected event has queued the generic admission; it
      // runs while the link is still forming, and the persisted pairing moves
      // on before it passes its checks.
      SharedPreferencesUtil().btDeviceSet(BtDevice(
        id: 'OTHER-PENDANT',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'OTHER-PENDANT'),
      ));
      async.elapse(const Duration(seconds: 15));

      expect(provider.isConnected, isFalse,
          reason: 'the racing generic admission must not publish the retired pairing');
      expect(SharedPreferencesUtil().btDevice.id, 'OTHER-PENDANT');
      reconciler.dispose();
      provider.dispose();
      async.flushTimers();
    });
  });

  test('a pairing persisted during device setup does not get the retired device published over it', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      nativeReplaysReady = true;
      final service = ServiceManager.instance().device;
      service.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 5));
      expect(service.connectionFor(_deviceId)?.status, DeviceConnectionState.connected);

      final provider = DeviceProvider();
      // Every step of device setup that touches the link re-checks it via
      // ensureConnection -> isConnected. Park the *second* such check (the
      // one after admission) and drift the persisted pairing while it is
      // parked — exactly the window the Ray-Ban input picker creates when it
      // persists a new microphone before awaiting its own connection.
      var linkChecks = 0;
      final linkCheckBlocked = Completer<void>();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMessageHandler('dev.flutter.pigeon.omi_pigeon.BleHostApi.isPeripheralConnected', (message) async {
        linkChecks++;
        if (linkChecks == 2) {
          await linkCheckBlocked.future;
        }
        return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[true]);
      });
      final reconciler = NativeLinkReconciler(provider, nativeLinkProbe: (_) async => true);

      reconciler.reconcile();
      async.elapse(const Duration(seconds: 5));
      // Device setup is parked mid-setup; the persisted pairing moves on
      // inside the window.
      SharedPreferencesUtil().btDeviceSet(BtDevice(
        id: 'OTHER-PENDANT',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'OTHER-PENDANT'),
      ));
      linkCheckBlocked.complete();
      async.elapse(const Duration(seconds: 20));

      expect(SharedPreferencesUtil().btDevice.id, 'OTHER-PENDANT',
          reason: 'device setup must not publish the retired pairing over the newer choice');
      reconciler.dispose();
      provider.dispose();
      async.flushTimers();
    });
  });

  test('a provider-only disconnect lets the resume reconcile re-admit the live link', () {
    fakeAsync((async) {
      pairPendant();
      linkUp = true;
      nativeReplaysReady = true;
      ServiceManager.instance().device.ensureConnection(_deviceId, force: true);
      async.elapse(const Duration(seconds: 5));
      final provider = DeviceProvider();
      provider.nativeLink.reconcile();
      async.elapse(const Duration(seconds: 5));
      expect(provider.isConnected, isTrue);

      // e.g. onboarding's error path drops the mirror without a link loss.
      provider.setIsConnected(false);
      provider.nativeLink.reconcile();
      async.elapse(const Duration(seconds: 5));

      expect(provider.isConnected, isTrue);
      provider.dispose();
      async.flushTimers();
    });
  });
}
