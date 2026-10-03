import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:fake_async/fake_async.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/capture/capture_ingress_health.dart';

void main() {
  const device = 'ingress-test';
  final now = DateTime.fromMillisecondsSinceEpoch(100000);
  String snapshot({String phase = 'flowing', bool confirmed = true}) => jsonEncode({
        'phase': phase,
        'generation': 'current-connection',
        'reason': 'audio_observed',
        'valid_until_ms': 130000,
        'subscription_confirmed': confirmed,
        'unverified_since_ms': 0,
      });

  tearDown(() => BleBridge.instance.onPeripheralDisconnected(device, null));

  test('only a confirmed flowing lease proves capture; expiry fails closed', () {
    for (final phase in ['inactive', 'unverified', 'repairing', 'reconnecting', 'quiet', 'actionRequired']) {
      expect(CaptureIngressHealth.parse(snapshot(phase: phase))!.verifiedAt(now), isFalse);
    }
    expect(CaptureIngressHealth.parse(snapshot(confirmed: false))!.verifiedAt(now), isFalse);
    final flowing = CaptureIngressHealth.parse(snapshot())!;
    expect(flowing.verifiedAt(now), isTrue);
    expect(flowing.verifiedAt(now.add(const Duration(seconds: 30))), isFalse);
    expect(CaptureIngressHealth.parse('{}'), isNull);
    expect(CaptureIngressHealth.parse('broken'), isNull);
  });

  test('presentation expires even when no further native event arrives', () {
    fakeAsync((async) {
      final bridge = BleBridge.instance;
      var changes = 0;
      void changed() => changes++;
      bridge.addIngressListener(changed);
      final packet = jsonDecode(snapshot()) as Map<String, dynamic>;
      packet['valid_until_ms'] = DateTime.now().millisecondsSinceEpoch + 30000;
      bridge.onCaptureHealth(device, jsonEncode(packet));
      expect(changes, 1);
      async.elapse(const Duration(seconds: 30));
      expect(changes, 2, reason: 'expiry itself must rebuild Listening surfaces');
      bridge.onDeviceReady(device, []);
      expect(bridge.ingressHealth(device), isNull);
      bridge.removeIngressListener(changed);
    });
  });

  test('cached services, readiness replay and working reads cannot restore capture truth', () {
    final bridge = BleBridge.instance;
    bridge.onCaptureHealth(device, snapshot());
    expect(bridge.ingressHealth(device)!.verifiedAt(now), isTrue);
    for (var launch = 0; launch < 5; launch++) {
      bridge.onDeviceReady(device, [
        BleService(uuid: 'cached-service', characteristicUuids: ['audio', 'battery'])
      ]);
      expect(bridge.ingressHealth(device), isNull);
      bridge.onCaptureHealth(device, snapshot(phase: 'unverified'));
      expect(bridge.ingressHealth(device)!.verifiedAt(now), isFalse);
    }
    bridge.onCaptureHealth(device, snapshot());
    expect(bridge.ingressHealth(device)!.verifiedAt(now), isTrue);
    bridge.onPeripheralDisconnected(device, null);
    expect(bridge.ingressHealth(device), isNull);
  });
}
