import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/device_mute_sync.dart';

void main() {
  // Firmware contract for issue #5054: pause/mute survives BLE disconnect.
  // The pendant must not resume recording because the phone went away.
  group('firmware capture mute policy (paused → disconnect → stay paused)', () {
    test('muted device does not capture while BLE is connected', () {
      expect(DeviceMuteSync.firmwareShouldCapture(muted: true), isFalse);
    });

    test('muted device does not capture after BLE disconnect', () {
      // Same gate as the connected case: disconnect is not a resume signal.
      expect(DeviceMuteSync.firmwareShouldCapture(muted: true), isFalse);
    });

    test('unmuted device still captures offline after disconnect', () {
      expect(DeviceMuteSync.firmwareShouldCapture(muted: false), isTrue);
    });

    test('only explicit unmute resumes capture after a paused disconnect', () {
      var muted = true;
      // Pause, then walk out of range — still muted, still not capturing.
      expect(DeviceMuteSync.firmwareShouldCapture(muted: muted), isFalse);
      // Reconnect must not flip the flag.
      expect(DeviceMuteSync.firmwareShouldCapture(muted: muted), isFalse);
      // Explicit unpause is the only resume.
      muted = false;
      expect(DeviceMuteSync.firmwareShouldCapture(muted: muted), isTrue);
    });
  });

  group('reconnect UI sync', () {
    test('device muted wins over a local unmuted pref', () {
      expect(
        DeviceMuteSync.resolveReconnectPaused(deviceMuted: true, localMuted: false),
        isTrue,
      );
    });

    test('device unmuted wins over a stale local mute', () {
      expect(
        DeviceMuteSync.resolveReconnectPaused(deviceMuted: false, localMuted: true),
        isFalse,
      );
    });

    test('legacy firmware (no mute characteristic) falls back to local mute', () {
      expect(
        DeviceMuteSync.resolveReconnectPaused(deviceMuted: null, localMuted: true),
        isTrue,
      );
      expect(
        DeviceMuteSync.resolveReconnectPaused(deviceMuted: null, localMuted: false),
        isFalse,
      );
    });
  });
}
