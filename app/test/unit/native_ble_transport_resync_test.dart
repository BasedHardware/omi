import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

class _FakeBleHostApi extends BleHostApi {
  final List<String> subscribed = [];
  Completer<void>? subscriptionResult;
  bool connected = true;
  int manages = 0;

  @override
  Future<bool> isPeripheralConnected(String uuid) async => connected;

  @override
  Future<void> manageDevice(String uuid, bool requiresBond) async {
    manages++;
  }

  @override
  Future<void> subscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {
    subscribed.add('$serviceUuid:$characteristicUuid');
    await subscriptionResult?.future;
  }

  @override
  Future<Uint8List> readCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async =>
      Uint8List.fromList([80]);

  @override
  Future<void> unsubscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {}
}

void main() {
  const uuid = 'AA:BB:CC:DD:EE:FF';
  const serviceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
  const charUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';

  final services = [
    BleService(uuid: serviceUuid, characteristicUuids: [charUuid]),
  ];

  late NativeBleTransport transport;

  setUp(() {
    transport = NativeBleTransport(uuid, hostApi: _FakeBleHostApi());
  });

  tearDown(() async {
    await transport.dispose();
  });

  test('missing characteristic failure reaches transport and a ready replay can retry', () async {
    await transport.dispose();
    final host = _FakeBleHostApi()..subscriptionResult = Completer<void>();
    transport = NativeBleTransport(uuid, hostApi: host);
    BleBridge.instance.onDeviceReady(uuid, []);
    final subscription = transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
    addTearDown(subscription.cancel);
    expect(host.subscribed, hasLength(1),
        reason: 'missing cached characteristic still has an observable native result');
    host.subscriptionResult!.completeError(StateError('NOT_FOUND'));
    await pumpEventQueue();
    expect(transport.subscriptionFailures, hasLength(1));
    final lateConsumer = <Object>[];
    final errors = transport.audioSubscriptionErrors.listen(lateConsumer.add);
    await pumpEventQueue();
    expect(lateConsumer, hasLength(1), reason: 'capture can bind after adapter connection setup');
    addTearDown(errors.cancel);
    host.subscriptionResult = null;
    BleBridge.instance.onDeviceReady(uuid, services);
    await pumpEventQueue();
    expect(host.subscribed, hasLength(2));
    expect(transport.subscriptionFailures, isEmpty);
  });

  test('late confirmation from a retired ready generation cannot confirm its replacement', () async {
    await transport.dispose();
    final old = Completer<void>();
    final current = Completer<void>();
    final host = _FakeBleHostApi()..subscriptionResult = old;
    transport = NativeBleTransport(uuid, hostApi: host);
    BleBridge.instance.onDeviceReady(uuid, services);
    final subscription = transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
    addTearDown(subscription.cancel);
    host.subscriptionResult = current;
    BleBridge.instance.onDeviceReady(uuid, services);
    current.completeError(StateError('subscription rejected'));
    await pumpEventQueue();
    old.complete();
    await pumpEventQueue();
    expect(transport.subscriptionFailures, hasLength(1));
  });

  test('incident replay consumes the native transaction trace across repeated launches', () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    final trace = jsonDecode(File('test/fixtures/capture_recovery_trace.json').readAsStringSync()) as List;
    var resets = 0;
    var repairs = 0;
    var launches = 0;
    final states = <DeviceTransportState>[];
    StreamSubscription? audio;
    StreamSubscription? link;
    try {
      for (final step in trace) {
        switch (step['event']) {
          case 'launch':
            await audio?.cancel();
            await link?.cancel();
            await transport.dispose();
            transport = NativeBleTransport(uuid, hostApi: _FakeBleHostApi());
            BleBridge.instance.setNativeIngressOwner(uuid, true);
            link = transport.connectionStateStream.listen(states.add);
            audio = transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {
              fail('the incident has zero notifications');
            });
            launches++;
          case 'ready':
            BleBridge.instance.onDeviceReady(uuid, services);
          case 'read':
            expect(await transport.readCharacteristic(serviceUuid, charUuid), [80]);
          case 'health':
            BleBridge.instance.onCaptureHealth(uuid, jsonEncode(step['snapshot']));
            final health = BleBridge.instance.ingressHealth(uuid)!;
            expect(health.verifiedAt(DateTime.now()), isFalse);
            expect(health.actionable, isFalse);
          case 'disconnected':
            BleBridge.instance.onPeripheralDisconnected(uuid, 'capture_recovery');
            await pumpEventQueue();
            expect(states.last, DeviceTransportState.disconnected);
            expect(BleBridge.instance.preservesCaptureIntent(uuid), isTrue);
          case 'repair':
            repairs++;
          case 'connect':
            resets++;
        }
        await pumpEventQueue();
      }
      expect(launches, 4);
      expect(repairs, 1);
      expect(resets, 1);
      expect(BleBridge.instance.ingressHealth(uuid)!.phase, 'quiet');
      expect(BleBridge.instance.ingressHealth(uuid)!.reconnectSpent, isTrue);
    } finally {
      await audio?.cancel();
      await link?.cancel();
      debugDefaultTargetPlatformOverride = null;
    }
  });

  test('iOS Omi has no competing Dart subscription watchdog', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      fakeAsync((async) {
        transport.dispose();
        final host = _FakeBleHostApi();
        transport = NativeBleTransport(uuid, hostApi: host);
        BleBridge.instance.setNativeIngressOwner(uuid, true);
        BleBridge.instance.onDeviceReady(uuid, services);
        transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
        async.flushMicrotasks();
        async.elapse(const Duration(hours: 16));
        expect(host.subscribed, hasLength(1));
      });
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  test('OpenGlass shares the audio UUID but retains its bounded Dart watchdog', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      fakeAsync((async) {
        transport.dispose();
        final host = _FakeBleHostApi();
        transport = NativeBleTransport(uuid, hostApi: host);
        BleBridge.instance.onDeviceReady(uuid, services);
        transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 20));
        expect(host.subscribed, hasLength(2));
      });
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    for (final audio in [
      charUuid,
      beeAudioCharacteristicUuid,
      fieldyAudioCharacteristicUuid,
      friendPendantAudioCharacteristicUuid,
      limitlessRxCharUuid
    ]) {
      test('$platform $audio initial failure reaches capture and retries once', () {
        debugDefaultTargetPlatformOverride = platform;
        try {
          fakeAsync((async) {
            transport.dispose();
            final first = Completer<void>();
            final host = _FakeBleHostApi()..subscriptionResult = first;
            transport = NativeBleTransport(uuid, hostApi: host);
            final errors = <Object>[];
            transport.audioSubscriptionErrors.listen(errors.add);
            BleBridge.instance.onDeviceReady(uuid, [
              BleService(uuid: serviceUuid, characteristicUuids: [audio])
            ]);
            transport.getCharacteristicStream(serviceUuid, audio).listen((_) {});
            first.completeError(StateError('CCCD failed'));
            async.flushMicrotasks();
            expect(errors, hasLength(1));
            host.subscriptionResult = null;
            async.elapse(const Duration(seconds: 20));
            expect(host.subscribed, hasLength(2));
            expect(transport.subscriptionFailures, isEmpty);
          });
        } finally {
          debugDefaultTargetPlatformOverride = null;
        }
      });
    }
  }

  test('a delayed initial confirmation failure does not consume the retry while pending', () {
    fakeAsync((async) {
      transport.dispose();
      final first = Completer<void>();
      final host = _FakeBleHostApi()..subscriptionResult = first;
      transport = NativeBleTransport(uuid, hostApi: host);
      // Subscribe before ready, as adapters initialized by native reconnect do.
      transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
      BleBridge.instance.onDeviceReady(uuid, services);
      async.flushMicrotasks();
      async.elapse(const Duration(seconds: 15));
      expect(host.subscribed, hasLength(1));
      first.completeError(StateError('notification timeout'));
      async.flushMicrotasks();
      host.subscriptionResult = null;
      async.elapse(const Duration(seconds: 20));
      expect(host.subscribed, hasLength(2));
    });
  });

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    test('$platform missing subscription callbacks time out and retry only once', () {
      debugDefaultTargetPlatformOverride = platform;
      try {
        fakeAsync((async) {
          transport.dispose();
          final late = Completer<void>();
          final host = _FakeBleHostApi()..subscriptionResult = late;
          transport = NativeBleTransport(uuid, hostApi: host);
          final errors = <Object>[];
          transport.audioSubscriptionErrors.listen(errors.add);
          BleBridge.instance.onDeviceReady(uuid, services);
          transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
          async.flushMicrotasks();
          async.elapse(NativeBleTransport.subscriptionTimeout);
          expect(errors.single, isA<TimeoutException>());
          async.elapse(const Duration(seconds: 4));
          expect(host.subscribed, hasLength(2));
          async.elapse(const Duration(minutes: 1));
          expect(errors, hasLength(2));
          expect(host.subscribed, hasLength(2));
          late.complete(); // current-generation late confirmation clears only its own timeout
          async.flushMicrotasks();
          expect(transport.subscriptionFailures, isEmpty);
          expect(host.manages, 0, reason: 'a subscription timeout does not retire the native link');
        });
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });
  }

  test('late success clears its timeout without completing the replacement retry', () {
    fakeAsync((async) {
      transport.dispose();
      final old = Completer<void>();
      final replacement = Completer<void>();
      final host = _FakeBleHostApi()..subscriptionResult = old;
      transport = NativeBleTransport(uuid, hostApi: host);
      BleBridge.instance.onDeviceReady(uuid, services);
      transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
      async.flushMicrotasks();
      async.elapse(NativeBleTransport.subscriptionTimeout);
      host.subscriptionResult = replacement;
      async.elapse(const Duration(seconds: 4));
      old.complete();
      async.flushMicrotasks();
      expect(transport.subscriptionFailures, isEmpty);
      final retryFailure = StateError('retry failed');
      replacement.completeError(retryFailure);
      async.flushMicrotasks();
      expect(transport.subscriptionFailures.values.single, same(retryFailure));
      expect(host.subscribed, hasLength(2));
    });
  });

  test('late success cannot clear a newer connection generation failure', () {
    fakeAsync((async) {
      transport.dispose();
      final old = Completer<void>();
      final current = Completer<void>();
      final host = _FakeBleHostApi()..subscriptionResult = old;
      transport = NativeBleTransport(uuid, hostApi: host);
      BleBridge.instance.onDeviceReady(uuid, services);
      transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
      async.flushMicrotasks();
      async.elapse(NativeBleTransport.subscriptionTimeout);
      BleBridge.instance.onPeripheralDisconnected(uuid, 'capture_recovery');
      host.subscriptionResult = current;
      BleBridge.instance.onDeviceReady(uuid, services);
      async.flushMicrotasks();
      async.elapse(NativeBleTransport.subscriptionTimeout);
      final failure = transport.subscriptionFailures.values.single;
      old.complete();
      async.flushMicrotasks();
      expect(transport.subscriptionFailures.values.single, same(failure));
      current.complete();
      async.flushMicrotasks();
      expect(transport.subscriptionFailures, isEmpty);
    });
  });

  test('a repeated device-ready for a live link keeps existing subscribers streaming', () async {
    BleBridge.instance.onDeviceReady(uuid, services);
    transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});

    BleBridge.instance.onPeripheralDisconnected(uuid, null);
    BleBridge.instance.onDeviceReady(uuid, services);

    final received = <List<int>>[];
    final subscription = transport.getCharacteristicStream(serviceUuid, charUuid).listen(received.add);
    addTearDown(subscription.cancel);

    // Native re-emits ready when Dart asks to connect a link that is already up.
    BleBridge.instance.onDeviceReady(uuid, services);
    BleBridge.instance.onCharacteristicValueUpdated(uuid, serviceUuid, charUuid, Uint8List.fromList([1, 2, 3]));
    await Future<void>.delayed(Duration.zero);

    expect(received, [
      [1, 2, 3],
    ]);
  });

  test('device-ready after a disconnect restores the transport to connected', () async {
    BleBridge.instance.onDeviceReady(uuid, services);

    final states = <DeviceTransportState>[];
    final subscription = transport.connectionStateStream.listen(states.add);
    addTearDown(subscription.cancel);

    BleBridge.instance.onPeripheralDisconnected(uuid, null);
    BleBridge.instance.onDeviceReady(uuid, services);
    await Future<void>.delayed(Duration.zero);

    expect(states, [DeviceTransportState.disconnected, DeviceTransportState.connected]);
  });

  test('isBleAudioCharacteristicUuid covers wearable audio notify chars', () {
    expect(isBleAudioCharacteristicUuid(audioDataStreamCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(friendPendantAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(limitlessRxCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(beeAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(fieldyAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(plaudNotifyCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(batteryLevelCharacteristicUuid), isFalse);
    expect(isBleAudioCharacteristicUuid(plaudWriteCharUuid), isFalse);
  });

  test('after reconnect, silent audio CCCD is retried once then left dead', () {
    fakeAsync((async) {
      transport.dispose();
      final hostApi = _FakeBleHostApi();
      transport = NativeBleTransport(uuid, hostApi: hostApi);

      const audioChar = '19b10001-e8f2-537e-4f6c-d104768a1214';
      final audioServices = [
        BleService(uuid: serviceUuid, characteristicUuids: [audioChar]),
      ];

      BleBridge.instance.onDeviceReady(uuid, audioServices);
      transport.getCharacteristicStream(serviceUuid, audioChar).listen((_) {});
      async.flushMicrotasks();

      BleBridge.instance.onPeripheralDisconnected(uuid, null);
      BleBridge.instance.onDeviceReady(uuid, audioServices);
      async.flushMicrotasks();

      final subscribesBeforeWatch = hostApi.subscribed.where((s) => s.contains(audioChar)).length;
      expect(subscribesBeforeWatch, greaterThanOrEqualTo(1));

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      final afterFirstSilence = hostApi.subscribed.where((s) => s.contains(audioChar)).length;
      expect(afterFirstSilence, subscribesBeforeWatch + 1, reason: 'one CCCD resubscribe on silence');

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      expect(
        hostApi.subscribed.where((s) => s.contains(audioChar)).length,
        afterFirstSilence,
        reason: 'do not tight-loop resubscribe after the single retry',
      );
    });
  });

  test('initial audio subscription also retries a silent CCCD once', () {
    fakeAsync((async) {
      transport.dispose();
      final hostApi = _FakeBleHostApi();
      transport = NativeBleTransport(uuid, hostApi: hostApi);

      BleBridge.instance.onDeviceReady(uuid, services);
      transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});
      async.flushMicrotasks();

      final subscribesBeforeWatch = hostApi.subscribed.where((s) => s.contains(charUuid)).length;
      expect(subscribesBeforeWatch, 1);

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      expect(
        hostApi.subscribed.where((s) => s.contains(charUuid)).length,
        subscribesBeforeWatch + 1,
        reason: 'the first connection needs the same bounded CCCD recovery as a reconnect',
      );
    });
  });

  test('Bee audio UUID silence after reconnect still schedules one CCCD retry', () {
    fakeAsync((async) {
      transport.dispose();
      final hostApi = _FakeBleHostApi();
      transport = NativeBleTransport(uuid, hostApi: hostApi);

      final audioServices = [
        BleService(uuid: beeServiceUuid, characteristicUuids: [beeAudioCharacteristicUuid]),
      ];

      BleBridge.instance.onDeviceReady(uuid, audioServices);
      transport.getCharacteristicStream(beeServiceUuid, beeAudioCharacteristicUuid).listen((_) {});
      async.flushMicrotasks();

      BleBridge.instance.onPeripheralDisconnected(uuid, null);
      BleBridge.instance.onDeviceReady(uuid, audioServices);
      async.flushMicrotasks();

      final subscribesBeforeWatch =
          hostApi.subscribed.where((s) => s.toLowerCase().contains(beeAudioCharacteristicUuid.toLowerCase())).length;
      expect(subscribesBeforeWatch, greaterThanOrEqualTo(1));

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      expect(
        hostApi.subscribed.where((s) => s.toLowerCase().contains(beeAudioCharacteristicUuid.toLowerCase())).length,
        subscribesBeforeWatch + 1,
        reason: 'Bee audio UUID must be recognized so CCCD retry arms',
      );
    });
  });
}
