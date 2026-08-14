import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/capture_keepalive_policy.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/enums.dart';

void main() {
  test('location permission alone does not start the foreground keep-alive', () {
    expect(shouldStartForegroundTaskFromLocationPermission(), isFalse);
  });

  test('identifies Omi, pendant, Limitless, Bee, Fieldy, and Plaud audio characteristics', () {
    expect(isBleAudioCharacteristicUuid(audioDataStreamCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(friendPendantAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(limitlessRxCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(beeAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(fieldyAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(plaudNotifyCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(batteryLevelCharacteristicUuid), isFalse);
    expect(isBleAudioCharacteristicUuid(plaudWriteCharUuid), isFalse);
  });

  group('shouldHoldCaptureForegroundTask', () {
    final started = DateTime.utc(2026, 8, 14, 12);

    test('does not hold when capture is stopped, paused, or interrupted', () {
      for (final state in [
        RecordingState.stop,
        RecordingState.pause,
        RecordingState.interrupted,
        RecordingState.initialising,
      ]) {
        expect(
          shouldHoldCaptureForegroundTask(
            recordingState: state,
            lastAudioFrameAt: started,
            recordingStartedAt: started,
            now: started,
          ),
          isFalse,
          reason: '$state',
        );
      }
    });

    test('holds during startup grace before the first audio frame', () {
      expect(
        shouldHoldCaptureForegroundTask(
          recordingState: RecordingState.deviceRecord,
          lastAudioFrameAt: null,
          recordingStartedAt: started,
          now: started.add(const Duration(seconds: 2)),
        ),
        isTrue,
      );
    });

    test('does not hold after grace if no audio frames arrived', () {
      expect(
        shouldHoldCaptureForegroundTask(
          recordingState: RecordingState.deviceRecord,
          lastAudioFrameAt: null,
          recordingStartedAt: started,
          now: started.add(const Duration(seconds: 6)),
        ),
        isFalse,
      );
    });

    test('holds while recent wearable audio frames are flowing', () {
      expect(
        shouldHoldCaptureForegroundTask(
          recordingState: RecordingState.deviceRecord,
          lastAudioFrameAt: started.add(const Duration(seconds: 10)),
          recordingStartedAt: started,
          now: started.add(const Duration(seconds: 12)),
        ),
        isTrue,
      );
    });

    test('releases wearable keep-alive when audio has gone stale', () {
      expect(
        shouldHoldCaptureForegroundTask(
          recordingState: RecordingState.deviceRecord,
          lastAudioFrameAt: started,
          recordingStartedAt: started,
          now: started.add(const Duration(seconds: 6)),
        ),
        isFalse,
      );
    });

    test('re-acquires wearable keep-alive when frames resume after silence', () {
      final resumed = started.add(const Duration(seconds: 20));
      expect(
        shouldHoldCaptureForegroundTask(
          recordingState: RecordingState.deviceRecord,
          lastAudioFrameAt: resumed,
          recordingStartedAt: started,
          now: resumed,
        ),
        isTrue,
      );
    });

    test('holds phone-mic and system-audio for the whole session without frames', () {
      for (final state in [RecordingState.record, RecordingState.systemAudioRecord]) {
        expect(
          shouldHoldCaptureForegroundTask(
            recordingState: state,
            lastAudioFrameAt: null,
            recordingStartedAt: started,
            now: started.add(const Duration(minutes: 2)),
          ),
          isTrue,
          reason: '$state',
        );
      }
    });
  });

  test('audio resume after silence must re-sync when FGS is not held', () {
    expect(
      shouldResyncCaptureForegroundOnAudioFrame(
        currentlyHeld: false,
        recordingState: RecordingState.deviceRecord,
      ),
      isTrue,
    );
    expect(
      shouldResyncCaptureForegroundOnAudioFrame(
        currentlyHeld: true,
        recordingState: RecordingState.deviceRecord,
      ),
      isFalse,
    );
    expect(
      shouldResyncCaptureForegroundOnAudioFrame(
        currentlyHeld: false,
        recordingState: RecordingState.stop,
      ),
      isFalse,
    );
  });

  test('clears inherited audio timestamps at session boundaries', () {
    expect(shouldClearCaptureAudioTimestamp(wasLive: true, isLive: false), isTrue);
    expect(shouldClearCaptureAudioTimestamp(wasLive: false, isLive: true), isTrue);
    expect(shouldClearCaptureAudioTimestamp(wasLive: true, isLive: true), isFalse);
    expect(shouldClearCaptureAudioTimestamp(wasLive: false, isLive: false), isTrue);
  });

  group('shouldReconnectSttKeepAlive', () {
    final now = DateTime.utc(2026, 8, 14, 12);

    test('does not reconnect the websocket without recent audio frames', () {
      expect(
        shouldReconnectSttKeepAlive(
          recordingDeviceServiceReady: true,
          socketConnected: false,
          signedIn: true,
          hasRecordingDevice: true,
          isPhoneMicKeepAliveState: false,
          lastAudioFrameAt: null,
          now: now,
        ),
        isFalse,
      );
      expect(
        shouldReconnectSttKeepAlive(
          recordingDeviceServiceReady: true,
          socketConnected: false,
          signedIn: true,
          hasRecordingDevice: true,
          isPhoneMicKeepAliveState: false,
          lastAudioFrameAt: now.subtract(const Duration(seconds: 16)),
          now: now,
        ),
        isFalse,
      );
    });

    test('reconnects when a device is present and frames are recent', () {
      expect(
        shouldReconnectSttKeepAlive(
          recordingDeviceServiceReady: true,
          socketConnected: false,
          signedIn: true,
          hasRecordingDevice: true,
          isPhoneMicKeepAliveState: false,
          lastAudioFrameAt: now.subtract(const Duration(seconds: 3)),
          now: now,
        ),
        isTrue,
      );
    });

    test('skips when the socket is already connected or the user is signed out', () {
      expect(
        shouldReconnectSttKeepAlive(
          recordingDeviceServiceReady: true,
          socketConnected: true,
          signedIn: true,
          hasRecordingDevice: true,
          isPhoneMicKeepAliveState: false,
          lastAudioFrameAt: now,
          now: now,
        ),
        isFalse,
      );
      expect(
        shouldReconnectSttKeepAlive(
          recordingDeviceServiceReady: true,
          socketConnected: false,
          signedIn: false,
          hasRecordingDevice: true,
          isPhoneMicKeepAliveState: false,
          lastAudioFrameAt: now,
          now: now,
        ),
        isFalse,
      );
    });
  });
}
