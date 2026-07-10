import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/services/meta_wearables/meta_capture_watchdog.dart';

void main() {
  test('does not restart while DAT session is paused', () {
    final watchdog = MetaCaptureWatchdog();

    expect(watchdog.nextAction(MetaCaptureHealth.paused), MetaCaptureWatchdogAction.wait);
    expect(watchdog.nextDelay(MetaCaptureHealth.paused), Duration.zero);
  });

  test('restarts stopped and stale DAT sessions', () {
    final watchdog = MetaCaptureWatchdog();

    expect(watchdog.nextAction(MetaCaptureHealth.stopped), MetaCaptureWatchdogAction.restart);
    expect(watchdog.nextAction(MetaCaptureHealth.stale), MetaCaptureWatchdogAction.restart);
  });

  test('backs off repeated restart attempts', () {
    final watchdog = MetaCaptureWatchdog();

    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 1));
    watchdog.recordRestartAttempt();
    expect(watchdog.nextDelay(MetaCaptureHealth.stale), const Duration(seconds: 2));
    watchdog.recordRestartAttempt();
    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 4));
  });

  test('healthy frame resets restart attempts', () {
    final watchdog = MetaCaptureWatchdog();

    watchdog.recordRestartAttempt();
    watchdog.recordRestartAttempt();
    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 4));

    watchdog.recordHealthyFrame();

    expect(watchdog.nextAction(MetaCaptureHealth.streaming), MetaCaptureWatchdogAction.wait);
    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 1));
  });

  test('provider schedules restart when active DAT capture is stopped or stale', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: true,
      hasFrameSubscription: true,
    );
    provider.debugOnCaptureWatchdogRestartScheduled =
        (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}');
    provider.debugHandleStreamSessionStateForTest(StreamSessionState.stopped);

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: true,
      hasFrameSubscription: true,
      lastQueuedPhotoAt: DateTime(2026, 7, 5, 12, 0, 0),
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      now: DateTime(2026, 7, 5, 12, 0, 45),
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, <String>['stopped:1', 'stale:1']);
    provider.dispose();
  });

  test('provider does not restart before next capture interval can produce a queued frame', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: true,
      hasFrameSubscription: true,
      lastQueuedPhotoAt: DateTime(2026, 7, 5, 12, 0, 0),
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      now: DateTime(2026, 7, 5, 12, 0, 7),
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, isEmpty);
    provider.dispose();
  });

  test('capture frequency does not delay dead-stream recovery', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: true,
      hasFrameSubscription: true,
      captureInterval: MetaGlassesCaptureInterval.m5,
      lastQueuedPhotoAt: DateTime(2026, 7, 5, 12, 0, 0),
      lastStreamFrameEventAt: DateTime(2026, 7, 5, 12, 2, 35),
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      now: DateTime(2026, 7, 5, 12, 3, 0),
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, <String>['stale:1']);
    provider.dispose();
  });

  test('capture frequency allows quiet long intervals while stream frames are alive', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: true,
      hasFrameSubscription: true,
      captureInterval: MetaGlassesCaptureInterval.m5,
      lastQueuedPhotoAt: DateTime(2026, 7, 5, 12, 0, 0),
      lastStreamFrameEventAt: DateTime(2026, 7, 5, 12, 2, 55),
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      now: DateTime(2026, 7, 5, 12, 3, 0),
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, isEmpty);
    provider.dispose();
  });

  test('provider waits while DAT session is paused', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: true,
      hasFrameSubscription: true,
    );
    provider.debugOnCaptureWatchdogRestartScheduled =
        (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}');
    provider.debugHandleStreamSessionStateForTest(StreamSessionState.paused);

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.paused,
      hasPreviewTexture: false,
      hasFrameSubscription: false,
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, isEmpty);
    provider.dispose();
  });

  test('provider waits while thermal paused', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: false,
      hasFrameSubscription: false,
      thermalPaused: true,
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, isEmpty);
    provider.dispose();
  });

  test('provider does not fight bounded stream retry or fallback', () {
    final provider = MetaWearablesProvider();
    final scheduled = <String>[];

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: false,
      hasFrameSubscription: false,
      streamRetryScheduled: true,
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: false,
      hasFrameSubscription: false,
      micOnlyFallback: true,
    );
    provider.debugEvaluateCaptureWatchdogForTest(
      onRestartScheduled: (health, delay) => scheduled.add('${health.name}:${delay.inSeconds}'),
    );

    expect(scheduled, isEmpty);
    provider.dispose();
  });

  test('provider cancels pending watchdog restart when capture becomes inactive', () {
    final provider = MetaWearablesProvider();

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: true,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: false,
      hasFrameSubscription: false,
    );
    provider.debugEvaluateCaptureWatchdogForTest();

    expect(provider.debugHasCaptureWatchdogTimerForTest, isTrue);

    provider.debugSetCaptureWatchdogStateForTest(
      isCapturing: false,
      streamSessionState: StreamSessionState.streaming,
      deviceSessionState: DeviceSessionState.started,
      hasPreviewTexture: false,
      hasFrameSubscription: false,
    );
    provider.debugEvaluateCaptureWatchdogForTest();

    expect(provider.debugHasCaptureWatchdogTimerForTest, isFalse);
    provider.dispose();
  });

  test('provider marks watchdog healthy only after queue enqueue succeeds', () {
    final source = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();
    final compact = source.replaceAll(RegExp(r'\s+'), ' ');

    expect(source, contains('Future<bool> _enqueuePhoto'));
    expect(source, contains('if (!queued)'));
    expect(source, contains('_lastQueuedPhotoAt = DateTime.now()'));
    expect(
      compact,
      contains(
          'if (!isCapturing || !_cameraStreamNeeded || _captureWatchdogPaused || micOnlyFallback || previewTextureId == null)'),
    );
    expect(source, contains('_cancelCaptureWatchdogTimer();\n      _markHealthRecovered();'));
    expect(compact,
        contains('if (!isCapturing || !_cameraStreamNeeded || _captureWatchdogPaused || micOnlyFallback) return;'));
    expect(source, contains('_frameForwardInFlight = false;'));
    expect(source, isNot(contains('void _onVideoFrame(VideoFrame frame) {\n    _markHealthRecovered();')));
  });

  test('watchdog backoff resets per capture session', () {
    // Review thread: a session that died after several restart attempts left
    // _attempts high, so the NEXT capture session inherited a 32s backoff.
    final watchdog = MetaCaptureWatchdog();
    watchdog.recordRestartAttempt();
    watchdog.recordRestartAttempt();
    watchdog.recordRestartAttempt();
    expect(watchdog.nextDelay(MetaCaptureHealth.stale).inSeconds, greaterThan(4));
    watchdog.reset();
    expect(watchdog.nextDelay(MetaCaptureHealth.stale).inSeconds, lessThanOrEqualTo(1),
        reason: 'a fresh capture session must start with fresh backoff');

    final provider = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();
    expect(provider, contains('_captureWatchdog.reset()'),
        reason: 'startCapture must reset restart backoff for the new session');
  });

  test('watchdog wait states re-check instead of going dormant', () {
    // Observed on-device 2026-07-05: after "wait reason=streamRetry" the
    // watchdog cancelled its timer and nothing re-armed it when the app was
    // suspended mid-retry — capture stayed dead until app relaunch. Every
    // wait branch must schedule a re-check so a foreground resume recovers.
    final provider = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();
    expect(provider, contains('_scheduleWatchdogRecheck'),
        reason: 'wait branches must re-arm a re-check timer, never cancel-and-return');
  });
}
