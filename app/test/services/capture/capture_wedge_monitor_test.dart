import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';

void main() {
  late DateTime now;
  late List<({String event, Map<String, Object> properties})> events;
  late List<String> retriedDevices;
  late bool flagEnabled;

  CaptureWedgeMonitor makeMonitor({
    Future<bool> Function()? featureGate,
    Future<void> Function(String deviceId)? bleRetry,
    Future<void> Function()? transferRetry,
    bool withRetry = false,
  }) {
    return CaptureWedgeMonitor(
      now: () => now,
      featureGate: featureGate ?? () async => flagEnabled,
      track: (event, properties) => events.add((event: event, properties: properties)),
      bleRetry: withRetry ? (bleRetry ?? ((deviceId) async => retriedDevices.add(deviceId))) : (_) async {},
      transferRetry: transferRetry,
      appBuild: () => '987',
      platform: () => 'ios',
    );
  }

  int connectedSession(CaptureWedgeMonitor monitor, {String deviceId = 'dev-a', String source = 'omi'}) {
    return monitor.onCaptureSessionConnected(deviceId: deviceId, source: source);
  }

  void zeroSession(CaptureWedgeMonitor monitor, {String deviceId = 'dev-a', String source = 'omi'}) {
    monitor.onCaptureSessionEnded(connectedSession(monitor, deviceId: deviceId, source: source), binaryBytesSent: 0);
  }

  void positiveSession(CaptureWedgeMonitor monitor, {String deviceId = 'dev-a', String source = 'omi'}) {
    final handle = connectedSession(monitor, deviceId: deviceId, source: source);
    monitor.onTranscriptObserved(deviceId);
    monitor.onCaptureSessionEnded(handle, binaryBytesSent: 320);
  }

  List<Map<String, Object>> forEvent(String name) =>
      events.where((e) => e.event == name).map((e) => e.properties).toList();

  setUp(() {
    now = DateTime(2026, 9, 25, 12);
    events = [];
    retriedDevices = [];
    flagEnabled = true;
  });

  group('zero-byte session streak', () {
    test('two zero-byte sessions do not declare a wedge', () async {
      final monitor = makeMonitor(withRetry: true);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Wedge Detected'), isEmpty);
      expect(retriedDevices, isEmpty);
    });

    test('three consecutive zero-byte sessions declare a wedge and run one retry', () async {
      final monitor = makeMonitor(withRetry: true);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();

      expect(monitor.visiblePrompt, isNotNull);
      expect(retriedDevices, ['dev-a']);
      final detected = forEvent('Capture Wedge Detected');
      expect(detected, hasLength(1));
      expect(detected.single['trigger'], 'zero_byte_streak');
      expect(detected.single['source'], 'omi');
      expect(detected.single['consecutive_zero_byte_sessions'], 3);
      expect(detected.single['app_build'], '987');
      expect(detected.single['platform'], 'ios');
    });

    test('three zero-byte sessions exactly 10 minutes apart declare', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      now = now.add(const Duration(minutes: 10));
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
    });

    test('three zero-byte sessions spanning more than 10 minutes do not declare', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      now = now.add(const Duration(minutes: 10) + const Duration(seconds: 1));
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('a positive-byte session resets the streak', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      positiveSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('an intentional session end does not count toward the streak', () async {
      final monitor = makeMonitor();
      monitor.onCaptureSessionEnded(connectedSession(monitor), binaryBytesSent: 0, intentional: true);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('an intentional session end does not reset the streak', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      monitor.onCaptureSessionEnded(connectedSession(monitor), binaryBytesSent: 0, intentional: true);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
    });

    test('a session that never reached connected does not count', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      monitor.onCaptureSessionEnded(9999, binaryBytesSent: 0);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('out-of-scope sources never track', () async {
      final monitor = makeMonitor();
      for (final source in const ['phone', 'openglass', 'onboarding', '']) {
        expect(monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: source), -1);
      }
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Wedge Detected'), isEmpty);
    });

    test('wedge state is isolated per device', () async {
      final monitor = makeMonitor();
      zeroSession(monitor, deviceId: 'dev-a');
      zeroSession(monitor, deviceId: 'dev-b');
      zeroSession(monitor, deviceId: 'dev-b');
      zeroSession(monitor, deviceId: 'dev-a');
      zeroSession(monitor, deviceId: 'dev-b');
      await pumpEventQueue();

      final episode = monitor.visiblePrompt;
      expect(episode, isNotNull);
      expect(episode!.deviceId, 'dev-b');
    });

    test('zero sessions spread days apart never accumulate into a wedge', () async {
      final monitor = makeMonitor();
      for (var i = 0; i < 8; i++) {
        zeroSession(monitor);
        now = now.add(const Duration(minutes: 11));
      }
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);

      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
    });

    test('detected telemetry reports the in-window count, not stale evicted ends', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      now = now.add(const Duration(minutes: 12));
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected').single['consecutive_zero_byte_sessions'], 3);
    });
  });

  group('rapid BLE drops', () {
    void bleDrop(
      CaptureWedgeMonitor monitor, {
      String deviceId = 'dev-a',
      Duration duration = const Duration(seconds: 3),
    }) {
      monitor.onBleSessionEnded(deviceId: deviceId, deviceType: DeviceType.omi, duration: duration);
    }

    test('three sub-15-second drops declare a rapid_reconnects wedge', () async {
      final monitor = makeMonitor(withRetry: true);
      bleDrop(monitor);
      bleDrop(monitor);
      bleDrop(monitor);
      await pumpEventQueue();

      expect(monitor.visiblePrompt, isNotNull);
      final detected = forEvent('Capture Wedge Detected');
      expect(detected.single['trigger'], 'rapid_reconnects');
      expect(detected.single['source'], 'omi');
      expect(retriedDevices, ['dev-a']);
    });

    test('a drop of exactly 15 seconds does not count (strict bound)', () async {
      final monitor = makeMonitor();
      bleDrop(monitor, duration: const Duration(seconds: 15));
      bleDrop(monitor);
      bleDrop(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('drops outside the rolling 5-minute window do not combine', () async {
      final monitor = makeMonitor();
      bleDrop(monitor);
      now = now.add(const Duration(minutes: 5) + const Duration(seconds: 1));
      bleDrop(monitor);
      bleDrop(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('drops at exactly the 5-minute window edge still count', () async {
      final monitor = makeMonitor();
      bleDrop(monitor);
      now = now.add(const Duration(minutes: 5));
      bleDrop(monitor);
      bleDrop(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
    });

    test('drops on different devices do not mix', () async {
      final monitor = makeMonitor();
      bleDrop(monitor, deviceId: 'dev-a');
      bleDrop(monitor, deviceId: 'dev-b');
      bleDrop(monitor, deviceId: 'dev-a');
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('friendPendant reports friend_com source', () async {
      final monitor = makeMonitor();
      for (var i = 0; i < 3; i++) {
        monitor.onBleSessionEnded(
          deviceId: 'dev-f',
          deviceType: DeviceType.friendPendant,
          duration: const Duration(seconds: 2),
        );
      }
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected').single['source'], 'friend_com');
    });

    test('unsupported device types are ignored', () async {
      final monitor = makeMonitor();
      for (var i = 0; i < 3; i++) {
        monitor.onBleSessionEnded(
          deviceId: 'dev-x',
          deviceType: DeviceType.openglass,
          duration: const Duration(seconds: 2),
        );
      }
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('a user-initiated disconnect does not count and clears a wedge', () async {
      final monitor = makeMonitor(withRetry: true);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);

      monitor.onBleSessionEnded(
        deviceId: 'dev-a',
        deviceType: DeviceType.omi,
        duration: const Duration(seconds: 30),
        intentional: true,
      );
      expect(monitor.visiblePrompt, isNull);
    });

    test('the retry-induced BLE end neither counts as a drop nor clears the episode', () async {
      final retryGate = Completer<void>();
      final monitor = makeMonitor(withRetry: true, bleRetry: (_) => retryGate.future);
      bleDrop(monitor);
      bleDrop(monitor);
      bleDrop(monitor);
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected'), hasLength(1));

      now = now.add(const Duration(minutes: 1));
      monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: const Duration(seconds: 2));
      retryGate.complete();
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);

      positiveSession(monitor);
      now = now.add(const Duration(minutes: 4) + const Duration(seconds: 30));
      monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: const Duration(seconds: 2));
      monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: const Duration(seconds: 2));
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected'), hasLength(1));
    });
  });

  group('transport bytes without transcript', () {
    void noTranscriptSession(CaptureWedgeMonitor monitor) {
      monitor.onCaptureSessionEnded(connectedSession(monitor), binaryBytesSent: 320);
    }

    test('three byte-producing sessions with no transcript declare an ungated wedge', () async {
      flagEnabled = false;
      final monitor = makeMonitor(withRetry: true);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      await pumpEventQueue();

      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerBytesSentNoTranscript);
      expect(retriedDevices, ['dev-a']);
      expect(forEvent('Capture Wedge Detected').single['trigger'], 'bytes_sent_no_transcript');
    });

    test('an observed transcript clears the no-transcript streak', () async {
      final monitor = makeMonitor();
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      positiveSession(monitor);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      await pumpEventQueue();

      expect(monitor.visiblePrompt, isNull);
    });

    test('connected watchdog declares while the byte-producing socket never ends', () async {
      var transferRetries = 0;
      final monitor = makeMonitor(transferRetry: () async => transferRetries++);
      final handle = connectedSession(monitor);
      monitor.onSocketBytesSent(handle, 640);

      now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      expect(transferRetries, 1);
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerBytesSentNoTranscript);
      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['bytes_since_last_transcript'], 640);
      expect(detected['socket_still_connected'], isTrue);
      monitor.dispose();
    });
  });

  group('upload silence', () {
    test('two-hour local backlog is surfaced and wakes transfer even with the legacy flag off', () async {
      var transferRetries = 0;
      flagEnabled = false;
      final monitor = makeMonitor(transferRetry: () async => transferRetries++);

      monitor.observeWalBacklog(pendingCount: 4, oldestPendingAt: now.subtract(const Duration(hours: 2)));
      await pumpEventQueue();

      expect(transferRetries, 1);
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerUploadSilence);
      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['pending_wal_count'], 4);
      expect(detected['oldest_pending_age_seconds'], 7200);
    });

    test('recent backlog stays quiet and a successful upload resolves an active episode', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: now.subtract(const Duration(minutes: 119)));
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);

      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: now.subtract(const Duration(hours: 3)));
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
      monitor.onUploadCompleted();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
    });
  });

  group('storage retention risk', () {
    test('cap engagement is surfaced once with eviction telemetry', () async {
      var transferRetries = 0;
      final monitor = makeMonitor(transferRetry: () async => transferRetries++);
      final engagedAt = now;

      monitor.observeStorageAtRisk(engagedAt: engagedAt, evictedCount: 3, retainedCount: 720);
      monitor.observeStorageAtRisk(engagedAt: engagedAt, evictedCount: 3, retainedCount: 720);
      await pumpEventQueue();

      expect(transferRetries, 1);
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerStorageAtRisk);
      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['evicted_wal_count'], 3);
      expect(detected['retained_wal_count'], 720);
      expect(detected['retention_policy'], 'oldest_first_count_cap');
      monitor.dispose();
    });
  });

  group('recovery lifecycle', () {
    test('prompt appears only after the single retry finishes', () async {
      final retryGate = Completer<void>();
      var retryStarted = 0;
      final monitor = makeMonitor(
        withRetry: true,
        bleRetry: (deviceId) async {
          retryStarted++;
          await retryGate.future;
        },
      );
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(retryStarted, 1);
      expect(monitor.visiblePrompt, isNull);
      retryGate.complete();
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
      expect(retryStarted, 1);
    });

    test('a failed retry still shows the prompt and never retries again', () async {
      var attempts = 0;
      final monitor = makeMonitor(
        withRetry: true,
        bleRetry: (deviceId) async {
          attempts++;
          throw StateError('ble down');
        },
      );
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(attempts, 1);
      expect(monitor.visiblePrompt, isNotNull);
      await pumpEventQueue();
      expect(attempts, 1);
    });

    test('dismissDeviceEpisode during an in-flight retry suppresses the prompt', () async {
      final retryGate = Completer<void>();
      final monitor = makeMonitor(withRetry: true, bleRetry: (deviceId) => retryGate.future);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      monitor.dismissDeviceEpisode('dev-a');
      retryGate.complete();
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
    });

    test('dismissDeviceEpisode clears a visible prompt', () async {
      final monitor = makeMonitor(withRetry: true);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
      monitor.dismissDeviceEpisode('dev-a');
      expect(monitor.visiblePrompt, isNull);
    });

    test('a positive session during retry resolves without a prompt', () async {
      final retryGate = Completer<void>();
      final monitor = makeMonitor(withRetry: true, bleRetry: (deviceId) => retryGate.future);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      positiveSession(monitor);
      retryGate.complete();
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
    });

    test('resolved fires once on the first positive session within 30 minutes', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();

      now = now.add(const Duration(minutes: 30));
      positiveSession(monitor);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
      positiveSession(monitor);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
      expect(monitor.visiblePrompt, isNull);
    });

    test('a positive session after 30 minutes clears the wedge without resolved', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();

      now = now.add(const Duration(minutes: 30) + const Duration(seconds: 1));
      positiveSession(monitor);
      expect(forEvent('Capture Recovery Resolved'), isEmpty);
      expect(monitor.visiblePrompt, isNull);
    });

    test('prompt shown telemetry fires once per episode', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      monitor.markPromptShown();
      monitor.markPromptShown();
      monitor.markPromptShown();
      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    test('actioned telemetry records the surface', () {
      final monitor = makeMonitor();
      monitor.onRecoveryActioned(surface: 'banner');
      expect(forEvent('Capture Recovery Actioned').single['surface'], 'banner');
    });
  });

  group('feature flag', () {
    test('flag off declares nothing: no wedge, retry, or telemetry', () async {
      flagEnabled = false;
      final monitor = makeMonitor(withRetry: true);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      for (var i = 0; i < 3; i++) {
        monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: const Duration(seconds: 2));
      }
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      expect(retriedDevices, isEmpty);
      expect(events, isEmpty);
    });

    test('a throwing feature gate fails closed', () async {
      final monitor = makeMonitor(featureGate: () async => throw StateError('no sdk'));
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Wedge Detected'), isEmpty);
    });

    test('a throwing track call does not break detection', () async {
      final monitor = CaptureWedgeMonitor(
        now: () => now,
        featureGate: () async => true,
        track: (event, properties) => throw StateError('analytics down'),
        bleRetry: (_) async {},
        appBuild: () => '1',
        platform: () => 'ios',
      );
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
    });
  });

  group('freshness', () {
    test('a fresh monitor has no wedge and no prompt', () {
      final monitor = makeMonitor();
      expect(monitor.visiblePrompt, isNull);
      expect(monitor.promptVisible, isFalse);
    });

    test('reset clears all device state', () async {
      final monitor = makeMonitor();
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
      monitor.reset();
      expect(monitor.visiblePrompt, isNull);
    });
  });
}
