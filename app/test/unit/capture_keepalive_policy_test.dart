import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

import 'package:omi/services/capture/capture_keepalive_policy.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/enums.dart';

void main() {
  test('location permission alone does not start the foreground keep-alive', () {
    expect(shouldStartForegroundTaskFromLocationPermission(), isFalse);
    // The production HomePage used to start FGS for these two values.
    expect(LocationPermission.always, isNot(LocationPermission.denied));
    expect(LocationPermission.whileInUse, isNot(LocationPermission.denied));
  });

  test('identifies Omi / pendant / Limitless audio characteristics', () {
    expect(isBleAudioCharacteristicUuid(audioDataStreamCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(friendPendantAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(limitlessRxCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(batteryLevelCharacteristicUuid), isFalse);
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

    test('holds while recent audio frames are flowing', () {
      expect(
        shouldHoldCaptureForegroundTask(
          recordingState: RecordingState.record,
          lastAudioFrameAt: started.add(const Duration(seconds: 10)),
          recordingStartedAt: started,
          now: started.add(const Duration(seconds: 12)),
        ),
        isTrue,
      );
    });

    test('releases the keep-alive when audio has gone stale', () {
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
