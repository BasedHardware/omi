import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/capture/capture_ingress_health.dart';

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

  for (final trigger in [
    CaptureWedgeMonitor.triggerConnectedNoBytes,
    CaptureWedgeMonitor.triggerZeroByteStreak,
    CaptureWedgeMonitor.triggerRapidReconnects,
  ]) {
    Future<CaptureWedgeMonitor> declare() async {
      final monitor = makeMonitor(withRetry: true);
      addTearDown(monitor.dispose);
      if (trigger == CaptureWedgeMonitor.triggerConnectedNoBytes) {
        connectedSession(monitor);
        now = now.add(CaptureWedgeMonitor.connectedNoBytesWindow);
        monitor.runConnectedWatchdog();
      } else {
        for (var i = 0; i < 3; i++) {
          if (trigger == CaptureWedgeMonitor.triggerZeroByteStreak) {
            zeroSession(monitor);
          } else {
            monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: Duration.zero);
          }
        }
      }
      await pumpEventQueue();
      expect(monitor.visiblePrompt?.trigger, trigger);
      return monitor;
    }

    test('$trigger resolves from sustained new BLE ingress without a transcript or socket', () async {
      final monitor = await declare();
      monitor.onBleIngressBytes('dev-b', 80);
      monitor.onBleIngressBytes('dev-a', 0);
      now = now.add(const Duration(seconds: 10));
      monitor.onBleIngressBytes('dev-a', 80);
      expect(monitor.visiblePrompt, isNotNull, reason: 'one packet is insufficient');
      now = now.add(const Duration(seconds: 6));
      monitor.onBleIngressBytes('dev-a', 80);
      expect(monitor.visiblePrompt, isNotNull, reason: 'a long gap restarts the proof window');
      for (var i = 0; i < 5; i++) {
        now = now.add(const Duration(seconds: 1));
        monitor.onBleIngressBytes('dev-a', 80);
      }
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Recovery Resolved').single['trigger'], trigger);
    });

    test('$trigger resolves only on fresh subscription-confirmed native flowing health', () async {
      final monitor = await declare();
      void health({String phase = 'flowing', bool subscribed = true, bool fresh = true}) {
        monitor.observeIngressHealth(
            'dev-a',
            CaptureIngressHealth(
              phase: phase,
              generation: 'recovered',
              reason: 'audio',
              validUntilMs: now.millisecondsSinceEpoch + (fresh ? 60000 : -1),
              subscriptionConfirmed: subscribed,
              unverifiedSinceMs: 0,
            ));
      }

      health(subscribed: false);
      expect(monitor.visiblePrompt, isNotNull);
      health(fresh: false);
      expect(monitor.visiblePrompt, isNotNull);
      health(phase: 'quiet');
      expect(monitor.visiblePrompt, isNotNull);
      now = now.add(const Duration(seconds: 1));
      health();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Recovery Resolved').single['trigger'], trigger);
    });
  }

  test('BLE recovery leaves simultaneous transcription and WAL recovery evidence intact', () async {
    final monitor = makeMonitor();
    addTearDown(monitor.dispose);
    for (var i = 0; i < 3; i++) {
      final handle = connectedSession(monitor);
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: 320);
      zeroSession(monitor);
    }
    monitor.observeWalBacklog(pendingCount: 1, oldestPendingAt: now.subtract(const Duration(hours: 3)));
    await pumpEventQueue();
    for (var i = 0; i < 6; i++) {
      now = now.add(const Duration(seconds: 1));
      monitor.onBleIngressBytes('dev-a', 80);
      monitor.onBleIngressBytes(CaptureWedgeMonitor.localWalDeviceId, 80);
    }
    expect(monitor.visiblePrompt, isNull);
    expect(forEvent('Capture Recovery Resolved').map((e) => e['trigger']), [CaptureWedgeMonitor.triggerZeroByteStreak]);
    monitor.onTranscriptObserved('dev-a');
    monitor.onUploadCompleted();
    expect(forEvent('Capture Recovery Resolved').map((e) => e['trigger']), [
      CaptureWedgeMonitor.triggerZeroByteStreak,
      CaptureWedgeMonitor.triggerBytesSentNoTranscript,
      CaptureWedgeMonitor.triggerUploadSilence,
    ]);
  });

  test('a cached native flowing lease cannot resolve a newly declared BLE episode', () async {
    final monitor = makeMonitor();
    addTearDown(monitor.dispose);
    final cached = CaptureIngressHealth(
      phase: 'flowing',
      generation: 'native-1',
      reason: 'audio',
      validUntilMs: now.add(const Duration(minutes: 1)).millisecondsSinceEpoch,
      subscriptionConfirmed: true,
      unverifiedSinceMs: 0,
    );
    monitor.observeIngressHealth('dev-a', cached);
    for (var i = 0; i < 3; i++) {
      zeroSession(monitor);
    }
    await pumpEventQueue();
    monitor.observeIngressHealth('dev-a', cached);
    expect(monitor.visiblePrompt, isNotNull);
  });

  test('BLE proof during an in-flight retry prevents its late completion from restoring the banner', () async {
    final retry = Completer<void>();
    final monitor = makeMonitor(withRetry: true, bleRetry: (_) => retry.future);
    addTearDown(monitor.dispose);
    for (var i = 0; i < 3; i++) {
      zeroSession(monitor);
    }
    await pumpEventQueue();
    for (var i = 0; i < 6; i++) {
      now = now.add(const Duration(seconds: 1));
      monitor.onBleIngressBytes('dev-a', 80);
    }
    expect(monitor.hasActiveEpisode('dev-a'), isFalse);
    retry.complete();
    await pumpEventQueue();
    expect(monitor.visiblePrompt, isNull);
    expect(forEvent('Capture Recovery Resolved'), hasLength(1));
  });

  test('BLE ingress and flowing health cannot clear storage-at-risk', () async {
    final monitor = makeMonitor();
    addTearDown(monitor.dispose);
    monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 1, retainedCount: 1, reason: 'disk_reserve');
    await pumpEventQueue();
    for (var i = 0; i < 6; i++) {
      now = now.add(const Duration(seconds: 1));
      monitor.onBleIngressBytes(CaptureWedgeMonitor.localWalDeviceId, 80);
    }
    monitor.observeIngressHealth(
        CaptureWedgeMonitor.localWalDeviceId,
        CaptureIngressHealth(
          phase: 'flowing',
          generation: 'native-1',
          reason: 'audio',
          validUntilMs: now.add(const Duration(minutes: 1)).millisecondsSinceEpoch,
          subscriptionConfirmed: true,
          unverifiedSinceMs: 0,
        ));
    expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerStorageAtRisk);
    expect(forEvent('Capture Recovery Resolved'), isEmpty);
  });

  test('batch suppresses transcript alarms and preserves BLE ingress recovery', () async {
    final monitor = makeMonitor(withRetry: true);
    addTearDown(monitor.dispose);
    final handle = connectedSession(monitor);
    monitor.onSocketBytesSent(handle, 320);
    monitor.setTranscriptExpected(handle, false);
    for (var minute = 0; minute < 3; minute++) {
      now = now.add(const Duration(minutes: 1));
      monitor.onBleIngressBytes('dev-a', 80);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();
    }
    expect(forEvent('Capture Wedge Detected'), isEmpty);
    now = now.add(CaptureWedgeMonitor.connectedNoBytesWindow);
    monitor.runConnectedWatchdog();
    await pumpEventQueue();
    expect(retriedDevices, ['dev-a']);
    expect(forEvent('Capture Wedge Detected').single['trigger'], CaptureWedgeMonitor.triggerConnectedNoBytes);
  });

  test('batch socket endings never create a zero-byte or no-transcript streak', () async {
    final monitor = makeMonitor(withRetry: true);
    addTearDown(monitor.dispose);
    for (var cycle = 0; cycle < 4; cycle++) {
      final handle = connectedSession(monitor);
      monitor.setTranscriptExpected(handle, false);
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: cycle.isEven ? 0 : 320);
    }
    await pumpEventQueue();
    expect(forEvent('Capture Wedge Detected'), isEmpty);
    expect(retriedDevices, isEmpty);
  });

  test('live handback gives transcript progress a fresh deadline', () async {
    final monitor = makeMonitor(withRetry: true);
    addTearDown(monitor.dispose);
    final handle = connectedSession(monitor);
    monitor.setTranscriptExpected(handle, false);
    now = now.add(const Duration(minutes: 4));
    monitor.onBleIngressBytes('dev-a', 80);
    monitor.setTranscriptExpected(handle, true);
    monitor.onSocketBytesSent(handle, 320);
    monitor.runConnectedWatchdog();
    await pumpEventQueue();
    expect(forEvent('Capture Wedge Detected'), isEmpty);
    now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
    monitor.runConnectedWatchdog();
    await pumpEventQueue();
    expect(forEvent('Capture Wedge Detected').single['trigger'], CaptureWedgeMonitor.triggerBytesSentNoTranscript);
  });

  test('native recovery owns retries and only exhausted failure projects a banner', () async {
    final monitor = makeMonitor(withRetry: true);
    addTearDown(monitor.dispose);
    monitor.setNativeIngressOwner('dev-a', true);
    CaptureIngressHealth health(String phase) => CaptureIngressHealth(
          phase: phase,
          generation: 'epoch-1',
          reason: phase,
          validUntilMs: phase == 'flowing' ? now.millisecondsSinceEpoch + 60000 : 0,
          subscriptionConfirmed: phase == 'quiet',
          unverifiedSinceMs: 1234,
        );
    for (final phase in ['unverified', 'repairing', 'reconnecting', 'quiet']) {
      monitor.observeIngressHealth('dev-a', health(phase));
      zeroSession(monitor);
      monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: Duration.zero);
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      expect(retriedDevices, isEmpty);
    }
    monitor.observeIngressHealth('dev-a', health('actionRequired'));
    expect(monitor.visiblePrompt!.trigger, CaptureWedgeMonitor.triggerIngressRecoveryFailed);
    monitor.onTranscriptObserved('dev-a');
    expect(monitor.visiblePrompt, isNotNull, reason: 'cached transcripts do not prove current audio ingress');
    monitor.retryVisibleEpisode();
    await pumpEventQueue();
    expect(retriedDevices, isEmpty, reason: 'banner must not bypass native persistent budget');
    monitor.observeIngressHealth('dev-a', health('flowing'));
    expect(monitor.visiblePrompt, isNull);
    expect(forEvent('Capture Ingress Health').singleWhere((e) => e['phase'] == 'actionRequired')['build'], '987');
    expect(forEvent('Capture Ingress Health').map((e) => e['phase']), [
      'unverified',
      'repairing',
      'reconnecting',
      'quiet',
      'actionRequired',
      'flowing',
    ]);
  });

  test('Android CCCD recovery suppresses legacy retries until acknowledgement clears it', () async {
    final monitor = makeMonitor(withRetry: true);
    addTearDown(monitor.dispose);
    monitor.observeIngressHealth(
      'dev-a',
      const CaptureIngressHealth(
        phase: 'recovering',
        generation: 'android',
        reason: CaptureIngressHealth.cccdRecoveryReason,
        validUntilMs: 0,
        subscriptionConfirmed: false,
        unverifiedSinceMs: 1,
      ),
    );
    for (var i = 0; i < 6; i++) {
      zeroSession(monitor);
      monitor.onBleSessionEnded(deviceId: 'dev-a', deviceType: DeviceType.omi, duration: Duration.zero);
    }
    await pumpEventQueue();
    expect(monitor.visiblePrompt, isNull);
    expect(retriedDevices, isEmpty);
    monitor.observeIngressHealth('dev-a', null);
    for (var i = 0; i < 3; i++) {
      zeroSession(monitor);
    }
    await pumpEventQueue();
    expect(retriedDevices, ['dev-a'], reason: 'healthy Android regains its ordinary watchdog');
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
      expect(detected.single['build'], '987');
      expect(detected.single['platform'], 'ios');
      expect(detected.single['seconds_since_last_ingress_byte'], -1);
      expect(detected.single['seconds_since_last_transcript'], -1);
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

    test('native ownership arriving while the feature gate is pending blocks the declaration', () async {
      final gate = Completer<bool>();
      final monitor = makeMonitor(featureGate: () => gate.future, withRetry: true);
      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor); // streak reached; declaration waits on the gate
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected'), isEmpty);

      // Ownership lands while the gate is still pending.
      monitor.setNativeIngressOwner('dev-a', true);
      gate.complete(true);
      await pumpEventQueue();

      // The legacy episode must not be declared behind native ownership: it
      // would be invisible (owner guard hides it) yet block later declarations.
      expect(forEvent('Capture Wedge Detected'), isEmpty);
      expect(retriedDevices, isEmpty);
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
      expect(detected.single['build'], '987');
      expect(detected.single['seconds_since_last_ingress_byte'], -1);
      expect(detected.single['seconds_since_last_transcript'], -1);
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

    test('three byte-producing sessions with no transcript track and retry without a prompt', () async {
      flagEnabled = false;
      final monitor = makeMonitor(withRetry: true);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      await pumpEventQueue();

      expect(monitor.visiblePrompt, isNull);
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

    test('a transcript during an ingress alert still releases the telemetry slot', () async {
      final monitor = makeMonitor(withRetry: true);
      monitor.setNativeIngressOwner('dev-a', true);
      monitor.observeIngressHealth(
        'dev-a',
        const CaptureIngressHealth(
          phase: 'actionRequired',
          generation: 'epoch-1',
          reason: 'recovery_exhausted',
          validUntilMs: 0,
          subscriptionConfirmed: false,
          unverifiedSinceMs: 1234,
        ),
      );
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerIngressRecoveryFailed);

      // A byte-producing session with no transcript declares the telemetry-only
      // episode natively-owned devices can still get.
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      await pumpEventQueue();

      // Transcript arrives during the alert: the ingress failure must stay
      // (native owns it), but the telemetry slot must be released so later
      // declarations are not blocked.
      monitor.onTranscriptObserved('dev-a');
      await pumpEventQueue();

      expect(
        monitor.visiblePrompt?.trigger,
        CaptureWedgeMonitor.triggerIngressRecoveryFailed,
        reason: 'the ingress failure stays owned by native recovery',
      );
      // The telemetry episode is gone; three more no-transcript sessions can
      // declare a fresh one instead of being blocked by the stale slot.
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      noTranscriptSession(monitor);
      await pumpEventQueue();
      expect(
        forEvent('Capture Wedge Detected').where((e) => e['trigger'] == 'bytes_sent_no_transcript'),
        isNotEmpty,
        reason: 'a stale telemetry slot must not block later declarations',
      );
    });

    test('two minutes of byte-producing silence tracks and retries without a prompt', () async {
      var transferRetries = 0;
      final monitor = makeMonitor(transferRetry: () async => transferRetries++);
      final handle = connectedSession(monitor);
      monitor.onSocketBytesSent(handle, 640);

      now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      expect(transferRetries, 1);
      expect(monitor.visiblePrompt, isNull);
      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['trigger'], CaptureWedgeMonitor.triggerBytesSentNoTranscript);
      expect(detected['bytes_since_last_transcript'], 640);
      expect(detected['socket_still_connected'], isTrue);
      monitor.dispose();
    });

    test('a zero-byte streak stays actionable alongside a quiet no-transcript episode', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      final handle = connectedSession(monitor);
      monitor.onSocketBytesSent(handle, 640);
      now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);

      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerZeroByteStreak);
      expect(forEvent('Capture Wedge Detected'), hasLength(2));

      positiveSession(monitor);
      expect(
        forEvent('Capture Recovery Resolved').map((event) => event['trigger']),
        containsAll([CaptureWedgeMonitor.triggerBytesSentNoTranscript, CaptureWedgeMonitor.triggerZeroByteStreak]),
      );
      expect(forEvent('Capture Recovery Resolved'), hasLength(2));
      monitor.dispose();
    });

    test('a completed telemetry retry cannot clear an overlapping BLE retry', () async {
      final telemetryRetry = Completer<void>();
      final bleRetry = Completer<void>();
      var transferStarted = 0;
      var bleStarted = 0;
      final monitor = makeMonitor(
        withRetry: true,
        transferRetry: () {
          transferStarted++;
          return telemetryRetry.future;
        },
        bleRetry: (_) {
          bleStarted++;
          return bleRetry.future;
        },
      );
      final handle = connectedSession(monitor);
      monitor.onSocketBytesSent(handle, 640);
      now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();
      expect(transferStarted, 1);

      zeroSession(monitor);
      zeroSession(monitor);
      zeroSession(monitor);
      await pumpEventQueue();
      expect(bleStarted, 1);
      expect(monitor.visiblePrompt, isNull);

      telemetryRetry.complete();
      await pumpEventQueue();
      monitor.onBleSessionEnded(
        deviceId: 'dev-a',
        deviceType: DeviceType.omi,
        duration: const Duration(seconds: 2),
        intentional: true,
      );
      bleRetry.complete();
      await pumpEventQueue();

      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerZeroByteStreak);
      monitor.dispose();
    });

    test('a telemetry-only episode does not count as active for BLE reconnect', () async {
      final monitor = makeMonitor(withRetry: true, transferRetry: () async {});
      final handle = connectedSession(monitor);
      monitor.onSocketBytesSent(handle, 640);
      now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();
      expect(monitor.hasActiveEpisode('dev-a'), isFalse);
      monitor.dispose();
    });
  });

  group('connected no bytes', () {
    test('five minutes with zero ingress bytes declares connected_no_bytes once', () async {
      final monitor = makeMonitor(withRetry: true);
      connectedSession(monitor, deviceId: 'pendant-9');

      now = now.add(const Duration(minutes: 4, seconds: 59));
      monitor.runConnectedWatchdog();
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected'), isEmpty);

      now = now.add(const Duration(seconds: 1));
      monitor.runConnectedWatchdog();
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      expect(retriedDevices, ['pendant-9']);
      final detected = forEvent('Capture Wedge Detected');
      expect(detected, hasLength(1));
      expect(detected.single['trigger'], CaptureWedgeMonitor.triggerConnectedNoBytes);
      expect(detected.single['build'], '987');
      expect(detected.single['seconds_since_last_ingress_byte'], -1);
      expect(detected.single['seconds_since_last_transcript'], -1);
      expect(detected.single['ingress_bytes'], 0);
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerConnectedNoBytes);
      monitor.dispose();
    });

    test('ingress bytes resuming before five minutes do not declare', () async {
      final monitor = makeMonitor(withRetry: true);
      connectedSession(monitor);

      now = now.add(const Duration(minutes: 4, seconds: 30));
      monitor.onBleIngressBytes('dev-a', 40);
      now = now.add(const Duration(minutes: 4, seconds: 59));
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      expect(forEvent('Capture Wedge Detected'), isEmpty);
      expect(retriedDevices, isEmpty);
      expect(monitor.visiblePrompt, isNull);
      monitor.dispose();
    });

    test('a native-owned silent link still retries the session device', () async {
      final monitor = makeMonitor(withRetry: true);
      monitor.setNativeIngressOwner('pendant-9', true);
      connectedSession(monitor, deviceId: 'pendant-9');
      now = now.add(CaptureWedgeMonitor.connectedNoBytesWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      expect(retriedDevices, ['pendant-9']);
      expect(forEvent('Capture Wedge Detected').single['trigger'], CaptureWedgeMonitor.triggerConnectedNoBytes);
      monitor.dispose();
    });

    test('an in-progress CCCD recovery is not declared again', () async {
      final monitor = makeMonitor(withRetry: true);
      monitor.observeIngressHealth(
        'dev-a',
        const CaptureIngressHealth(
          phase: 'recovering',
          generation: 'android',
          reason: CaptureIngressHealth.cccdRecoveryReason,
          validUntilMs: 0,
          subscriptionConfirmed: false,
          unverifiedSinceMs: 1,
        ),
      );
      connectedSession(monitor);
      now = now.add(CaptureWedgeMonitor.connectedNoBytesWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      expect(retriedDevices, isEmpty);
      expect(forEvent('Capture Wedge Detected'), isEmpty);
      monitor.dispose();
    });

    test('a late check reports the age of the last ingress byte', () async {
      final monitor = makeMonitor(withRetry: true);
      connectedSession(monitor);
      now = now.add(const Duration(minutes: 1));
      monitor.onBleIngressBytes('dev-a', 80);
      now = now.add(const Duration(minutes: 6));
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['trigger'], CaptureWedgeMonitor.triggerConnectedNoBytes);
      expect(detected['build'], '987');
      expect(detected['seconds_since_last_ingress_byte'], 360);
      expect(detected['seconds_since_last_transcript'], -1);
      monitor.dispose();
    });

    test('transcript age is measured from the transcript observation', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      final handle = connectedSession(monitor);
      monitor.onTranscriptObserved('dev-a');
      monitor.onSocketBytesSent(handle, 640);
      now = now.add(CaptureWedgeMonitor.connectedNoTranscriptWindow);
      monitor.runConnectedWatchdog();
      await pumpEventQueue();

      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['trigger'], CaptureWedgeMonitor.triggerBytesSentNoTranscript);
      expect(detected['seconds_since_last_transcript'], 120);
      expect(detected['seconds_since_last_ingress_byte'], -1);
      expect(detected['build'], '987');
      monitor.dispose();
    });
  });

  group('upload silence', () {
    test('two-hour local backlog tracks and wakes transfer without a prompt', () async {
      var transferRetries = 0;
      flagEnabled = false;
      final monitor = makeMonitor(transferRetry: () async => transferRetries++);

      monitor.observeWalBacklog(pendingCount: 4, oldestPendingAt: now.subtract(const Duration(hours: 2)));
      await pumpEventQueue();

      expect(transferRetries, 1);
      expect(monitor.visiblePrompt, isNull);
      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['pending_wal_count'], 4);
      expect(detected['oldest_pending_age_seconds'], 7200);
      expect(detected['build'], '987');
      expect(detected['seconds_since_last_ingress_byte'], -1);
      expect(detected['seconds_since_last_transcript'], -1);
    });

    test('recent backlog stays quiet and a successful upload resolves an active episode', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: now.subtract(const Duration(minutes: 119)));
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);

      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: now.subtract(const Duration(hours: 3)));
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);
      monitor.onUploadCompleted();
      expect(monitor.visiblePrompt, isNull);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
    });
  });

  group('storage retention risk', () {
    test('count cap emits diagnostic telemetry once without a prompt or recovery', () async {
      var transferRetries = 0;
      final monitor = makeMonitor(transferRetry: () async => transferRetries++);
      final engagedAt = now;

      monitor.observeStorageAtRisk(engagedAt: engagedAt, blockedCount: 3, retainedCount: 720, reason: 'count_cap');
      monitor.observeStorageAtRisk(engagedAt: engagedAt, blockedCount: 3, retainedCount: 720, reason: 'count_cap');
      await pumpEventQueue();

      expect(transferRetries, 0);
      expect(monitor.visiblePrompt, isNull);
      final detected = forEvent('Capture Wedge Detected').single;
      expect(detected['blocked_wal_count'], 3);
      expect(detected['retained_wal_count'], 720);
      expect(detected['retention_policy'], 'admission_count_cap');
      monitor.dispose();
    });

    for (final reason in ['disk_reserve', 'disk_space_unknown']) {
      test('$reason still surfaces after count-cap diagnostics', () async {
        var transferRetries = 0;
        final monitor = makeMonitor(transferRetry: () async => transferRetries++);
        monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 1, retainedCount: 720, reason: 'count_cap');
        await pumpEventQueue();
        expect(monitor.visiblePrompt, isNull);
        monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 1, retainedCount: 720, reason: reason);
        await pumpEventQueue();
        expect(transferRetries, 1);
        expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerStorageAtRisk);
        expect(forEvent('Capture Wedge Detected').map((event) => event['block_reason']), ['count_cap', reason]);
        monitor.dispose();
      });
    }

    test('storage risk stays visible alongside a quiet upload episode', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: now.subtract(const Duration(hours: 3)));
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull);

      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerStorageAtRisk);
      expect(forEvent('Capture Wedge Detected'), hasLength(2));
      monitor.onUploadCompleted();
      expect(
        forEvent('Capture Recovery Resolved').map((event) => event['trigger']),
        containsAll([CaptureWedgeMonitor.triggerUploadSilence, CaptureWedgeMonitor.triggerStorageAtRisk]),
      );
      expect(forEvent('Capture Recovery Resolved'), hasLength(2));
      // The episodes resolved, but upload progress proves nothing about the
      // disk: the storage ROW — what Activity and the bell read — must survive
      // while the retention risk keeps refusing recordings.
      expect(monitor.storageAtRisk, isNotNull, reason: 'upload progress must not clear the storage row');
      expect(monitor.hasCaptureAttention, isTrue);
      expect(monitor.hasUnseenCaptureAttention.value, isTrue, reason: 'the bell keeps warning about the disk');

      monitor.clearStorageAtRisk();
      expect(monitor.storageAtRisk, isNull);
      expect(monitor.hasCaptureAttention, isFalse);
    });
  });

  group('capture attention rows', () {
    test('disk admission failure engages the storage row with its counts', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      final engagedAt = now.subtract(const Duration(minutes: 30));

      monitor.observeStorageAtRisk(engagedAt: engagedAt, blockedCount: 3, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();

      expect(monitor.hasCaptureAttention, isTrue);
      expect(monitor.storageAtRisk?.engagedAt, engagedAt);
      expect(monitor.storageAtRisk?.blockedCount, 3);
      expect(monitor.storageAtRisk?.retainedCount, 720);
      expect(monitor.storageAtRisk?.reason, 'disk_reserve');
      monitor.dispose();
    });

    test('count-cap pressure never engages the storage row', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 3, retainedCount: 720, reason: 'count_cap');
      await pumpEventQueue();
      expect(monitor.storageAtRisk, isNull);
      expect(monitor.hasCaptureAttention, isFalse);
      monitor.dispose();
    });

    test('count-cap pressure ends a storage row a disk failure engaged, and disk failure re-engages it', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 3, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();
      expect(monitor.storageAtRisk, isNotNull, reason: 'the disk refused recordings');

      // The disk admitted a write again but >= 720 unsynced WALs remain: the risk
      // is count pressure now, which is diagnostic only. The row must not keep
      // claiming storage is full and recordings are paused.
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 3, retainedCount: 720, reason: 'count_cap');
      await pumpEventQueue();
      expect(monitor.storageAtRisk, isNull, reason: 'count pressure never owns the storage row');
      expect(monitor.hasCaptureAttention, isFalse);

      // A disk failure that returns re-engages the row: its reason differs, so
      // the fingerprint dedupe does not swallow it.
      now = now.add(const Duration(minutes: 5));
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 4, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();
      expect(monitor.storageAtRisk?.blockedCount, 4, reason: 'a returning disk failure re-engages the row');
      monitor.dispose();
    });

    test('storage counts refresh while the episode slot is already held', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();
      expect(forEvent('Capture Wedge Detected'), hasLength(1));

      // A later observation with different counts: no second alert, but the row tells the truth.
      now = now.add(const Duration(minutes: 10));
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 7, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();

      expect(forEvent('Capture Wedge Detected'), hasLength(1), reason: 'one episode, not a second alert');
      expect(monitor.storageAtRisk?.blockedCount, 7);
      monitor.dispose();
    });

    test('an upload stall engages the row with kept-audio seconds, then refreshes counts', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      final stalledAt = now;
      monitor.observeWalBacklog(
          pendingCount: 5, oldestPendingAt: now.subtract(const Duration(hours: 3)), pendingSeconds: 47 * 60);
      await pumpEventQueue();

      expect(monitor.uploadStall?.pendingCount, 5);
      expect(monitor.uploadStall?.pendingSeconds, 47 * 60);
      expect(monitor.uploadStall?.since, stalledAt);
      expect(monitor.hasCaptureAttention, isTrue);

      now = now.add(const Duration(minutes: 20));
      monitor.observeWalBacklog(
          pendingCount: 6, oldestPendingAt: now.subtract(const Duration(minutes: 200)), pendingSeconds: 50 * 60);
      await pumpEventQueue();

      expect(monitor.uploadStall?.pendingCount, 6, reason: 'the row shows the latest backlog');
      expect(monitor.uploadStall?.since, stalledAt, reason: 'the stall keeps when it began');
      monitor.dispose();
    });

    test('the row ends once nothing waiting is old enough to be stalled', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeWalBacklog(
          pendingCount: 5, oldestPendingAt: now.subtract(const Duration(hours: 3)), pendingSeconds: 47 * 60);
      await pumpEventQueue();
      expect(monitor.uploadStall?.pendingCount, 5);

      // The stalled recordings were deleted or ran out of retries; one new recording is waiting.
      now = now.add(const Duration(minutes: 20));
      monitor.observeWalBacklog(
          pendingCount: 1, oldestPendingAt: now.subtract(const Duration(minutes: 10)), pendingSeconds: 60);
      await pumpEventQueue();

      expect(monitor.uploadStall, isNull);
      expect(monitor.hasCaptureAttention, isFalse);
      monitor.dispose();
    });

    test('a backlog under the silence threshold never engages the row', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeWalBacklog(
          pendingCount: 5, oldestPendingAt: now.subtract(const Duration(minutes: 119)), pendingSeconds: 600);
      await pumpEventQueue();
      expect(monitor.uploadStall, isNull);
      expect(monitor.hasCaptureAttention, isFalse);
      monitor.dispose();
    });

    test('an empty backlog and a finished upload both resolve the rows', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 2, retainedCount: 720, reason: 'disk_reserve');
      monitor.observeWalBacklog(
          pendingCount: 5, oldestPendingAt: now.subtract(const Duration(hours: 3)), pendingSeconds: 600);
      await pumpEventQueue();
      expect(monitor.hasCaptureAttention, isTrue);

      monitor.onUploadCompleted();
      expect(monitor.uploadStall, isNull);
      // Upload progress is not disk recovery: the storage row survives it.
      expect(monitor.storageAtRisk, isNotNull);
      expect(monitor.hasCaptureAttention, isTrue);
      monitor.clearStorageAtRisk();
      expect(monitor.hasCaptureAttention, isFalse);

      // Hours later the disk is still full: a fresh engagement brings the row back.
      now = now.add(const Duration(hours: 3));
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 2, retainedCount: 720, reason: 'disk_reserve');
      monitor.observeWalBacklog(
          pendingCount: 4, oldestPendingAt: now.subtract(const Duration(hours: 3)), pendingSeconds: 600);
      await pumpEventQueue();
      expect(monitor.hasCaptureAttention, isTrue);

      monitor.observeWalBacklog(pendingCount: 0, oldestPendingAt: null);
      expect(monitor.uploadStall, isNull, reason: 'an empty backlog ends the upload row');
      expect(monitor.storageAtRisk, isNotNull, reason: 'the disk is still full; only its own observation ends the row');
      monitor.clearStorageAtRisk();
      expect(monitor.hasCaptureAttention, isFalse);
      monitor.dispose();
    });

    test('dismissing the local-wal episode ends the rows until a newly declared trigger', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 2, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();
      expect(monitor.storageAtRisk, isNotNull);

      monitor.dismissDeviceEpisode(CaptureWedgeMonitor.localWalDeviceId);
      expect(monitor.storageAtRisk, isNull);

      // Same observation again: the fingerprint guard keeps it hidden, as the banner did.
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 2, retainedCount: 720, reason: 'disk_reserve');
      expect(monitor.storageAtRisk, isNull);

      now = now.add(const Duration(minutes: 5));
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 4, retainedCount: 720, reason: 'disk_reserve');
      expect(monitor.storageAtRisk?.blockedCount, 4);
      monitor.dispose();
    });

    test('the bell: a new engagement lights it, Activity marks it seen, a new episode re-lights it', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      expect(monitor.hasUnseenCaptureAttention.value, isFalse);

      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 2, retainedCount: 720, reason: 'disk_reserve');
      expect(monitor.hasUnseenCaptureAttention.value, isTrue);

      now = now.add(const Duration(minutes: 5));
      monitor.markCaptureAttentionSeen();
      expect(monitor.hasUnseenCaptureAttention.value, isFalse);

      // The same condition persisting stays seen; a later engagement is news again.
      monitor.observeStorageAtRisk(
          engagedAt: now.add(const Duration(minutes: 1)), blockedCount: 3, retainedCount: 720, reason: 'disk_reserve');
      expect(monitor.hasUnseenCaptureAttention.value, isTrue);
      monitor.dispose();
    });

    test('marking seen through a build snapshot never swallows a newer incident', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      final builtAt = now;
      monitor.observeStorageAtRisk(engagedAt: builtAt, blockedCount: 2, retainedCount: 720, reason: 'disk_reserve');
      expect(monitor.hasUnseenCaptureAttention.value, isTrue);

      // The frame renders the row that existed at build time; an incident
      // declared after the build (before the post-frame callback runs) must
      // stay unseen — the bell keeps warning until a frame shows its row.
      now = now.add(const Duration(minutes: 1));
      monitor.markCaptureAttentionSeen(through: builtAt);
      expect(monitor.hasUnseenCaptureAttention.value, isFalse);

      now = now.add(const Duration(minutes: 1));
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 4, retainedCount: 720, reason: 'disk_reserve');
      monitor.markCaptureAttentionSeen(through: builtAt);
      expect(monitor.hasUnseenCaptureAttention.value, isTrue,
          reason: 'a stale callback cannot extinguish the bell for an incident it never rendered');

      // The seen timestamp never rewinds: marking through an older build is a no-op.
      monitor.markCaptureAttentionSeen();
      expect(monitor.hasUnseenCaptureAttention.value, isFalse);
      monitor.dispose();
    });

    test('reset clears the rows and the bell', () async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeWalBacklog(
          pendingCount: 5, oldestPendingAt: now.subtract(const Duration(hours: 3)), pendingSeconds: 600);
      await pumpEventQueue();
      expect(monitor.hasCaptureAttention, isTrue);
      expect(monitor.hasUnseenCaptureAttention.value, isTrue);

      monitor.reset();
      expect(monitor.hasCaptureAttention, isFalse);
      expect(monitor.hasUnseenCaptureAttention.value, isFalse);
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

    test('dismissVisibleEpisode keeps the telemetry-only episode for the same device', () async {
      // The tested combination: a visible storage-risk prompt and an unrelated
      // telemetry-only upload-silence operation, both on the local WAL state.
      final monitor = makeMonitor(withRetry: true, transferRetry: () async {});
      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: now.subtract(const Duration(hours: 3)));
      await pumpEventQueue();
      monitor.observeStorageAtRisk(engagedAt: now, blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNotNull);
      expect(forEvent('Capture Wedge Detected').map((e) => e['trigger']),
          containsAll([CaptureWedgeMonitor.triggerUploadSilence, CaptureWedgeMonitor.triggerStorageAtRisk]));

      monitor.dismissVisibleEpisode(CaptureWedgeMonitor.localWalDeviceId);

      expect(monitor.visiblePrompt, isNull, reason: 'the dismissed prompt is gone');
      // The telemetry operation survives: a later upload completion still
      // resolves it instead of it having been erased as if it never existed.
      expect(
        forEvent('Capture Recovery Resolved').map((e) => e['trigger']),
        isNot(contains(CaptureWedgeMonitor.triggerUploadSilence)),
        reason: 'the telemetry episode was not silently resolved by the dismissal',
      );
      monitor.onUploadCompleted();
      await pumpEventQueue();
      expect(
        forEvent('Capture Recovery Resolved').map((e) => e['trigger']),
        contains(CaptureWedgeMonitor.triggerUploadSilence),
        reason: 'the surviving telemetry episode resolves when the upload lands',
      );
    });

    test('a dismissed ingress episode stays dismissed across native re-ticks of the same incident', () async {
      CaptureIngressHealth snapshot(String generation) => CaptureIngressHealth(
            phase: 'actionRequired',
            generation: generation,
            reason: 'subscription_timeout',
            validUntilMs: 0,
            subscriptionConfirmed: false,
            unverifiedSinceMs: 60000,
          );
      final monitor = makeMonitor(withRetry: true);
      monitor.observeIngressHealth('dev-a', snapshot('g1'));
      await pumpEventQueue();
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerIngressRecoveryFailed);

      monitor.dismissVisibleEpisode('dev-a');
      expect(monitor.visiblePrompt, isNull, reason: 'the reader dismissed the incident');

      // iOS republishes the same actionable snapshot every ~5s: the dismissal
      // must hold for an unchanged incident instead of resurrecting the banner.
      monitor.observeIngressHealth('dev-a', snapshot('g1'));
      await pumpEventQueue();
      expect(monitor.visiblePrompt, isNull, reason: 'same generation re-tick does not resurrect the banner');

      // A new incident (new connection generation) alerts again.
      monitor.observeIngressHealth('dev-a', snapshot('g2'));
      await pumpEventQueue();
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerIngressRecoveryFailed,
          reason: 'a genuinely new incident is a new alert');
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
      expect(forEvent('Capture Recovery Resolved').single['build'], '987');
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
      expect(forEvent('Capture Recovery Prompt Shown').single['build'], '987');
    });

    test('actioned telemetry records the surface', () {
      final monitor = makeMonitor();
      monitor.onRecoveryActioned(surface: 'banner');
      expect(forEvent('Capture Recovery Actioned').single['surface'], 'banner');
      expect(forEvent('Capture Recovery Actioned').single['build'], '987');
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
