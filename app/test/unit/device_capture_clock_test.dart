import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/device_capture_clock.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/sdcard_wal_sync.dart';

void main() {
  final now = DateTime.utc(2026, 11, 15, 11);
  final seconds = now.millisecondsSinceEpoch ~/ 1000;

  test('import plausibility is inclusive at the floor and exactly +24h', () {
    expect(deviceCaptureTimePlausible(1704067200, seconds), isTrue);
    expect(deviceCaptureTimePlausible(seconds + 86400, seconds), isTrue);
    for (final invalid in [1704067199, 0, -1, seconds + 86401, 1967677260, 0x7fffffff, 0x80000000]) {
      expect(deviceCaptureTimePlausible(invalid, seconds), isFalse, reason: '$invalid');
    }
  });

  for (final invalid in [0, -1, 1704067199, seconds + 86401, 1967677260, 0x7fffffff]) {
    test('a complete imported file uses its decoded duration, not device $invalid', () {
      final clock = deviceFileCaptureClock(
        deviceSeconds: invalid,
        durationSeconds: 127,
        nowSeconds: seconds,
        enabled: true,
      );
      expect(clock.start, seconds - 127);
      expect(clock.run, matches(RegExp(r'^[0-9a-z]{1,32}$')));
      final continued = deviceFileCaptureClock(
        deviceSeconds: invalid,
        durationSeconds: 127,
        nowSeconds: seconds,
        existingRun: clock.run,
        enabled: true,
      );
      expect(continued, clock);
    });
  }

  test('a plausible device time is unchanged and has no invented run', () {
    final clock = deviceFileCaptureClock(
      deviceSeconds: seconds + 86400,
      durationSeconds: 127,
      nowSeconds: seconds,
      enabled: true,
    );
    expect(clock, (start: seconds + 86400, run: null));
  });

  test('an implausible phone cannot create a new estimate', () {
    for (final badPhone in [0, -1, 1704067199, 0x80000000]) {
      expect(() => estimatedDeviceStart(badPhone, 10, enabled: true), throwsStateError);
      // Positive device values keep the pre-change behavior: this phone cannot
      // demonstrate that they are in the future relative to a real clock.
      expect(useDeviceCaptureTime(1967677260, badPhone, enabled: true), isTrue);
    }
    expect(() => estimatedDeviceStart(1704067200, 1, enabled: true), throwsStateError);
    expect(() => estimatedDeviceStart(seconds, -1, enabled: true), throwsStateError);
  });

  test('kill switch OFF matches the old positive/unset predicates exactly', () {
    for (final raw in [1, 1704067199, seconds + 86401, 1967677260, 0x7fffffff]) {
      expect(deviceFileCaptureClock(deviceSeconds: raw, durationSeconds: 30, nowSeconds: seconds, enabled: false),
          (start: raw, run: null));
    }
    final unset = deviceFileCaptureClock(deviceSeconds: 0, durationSeconds: 30, nowSeconds: 0, enabled: false);
    expect(unset.start, -30);
    expect(unset.run, isNotNull);
  });

  test('ring 2038 boundary and uptime flag cannot be mistaken for UTC', () {
    expect(RingProtocol.readRecordTimestamp([0x7f, 0xff, 0xff, 0xff]), 0x7fffffff);
    expect(useDeviceCaptureTime(0x7fffffff, seconds, enabled: true), isFalse);
    expect(RingProtocol.readRecordTimestamp([0x80, 0, 0, 0]), 0);
    expect(RingProtocol.readRecordTimestamp([0x80, 0, 0, 10]), 0);
  });

  test('the legacy SD marker window agrees on every device-time boundary', () {
    for (final raw in [1704067200, seconds + 86400, seconds + 86401, 1967677260, 0x7fffffff, 0, -1]) {
      expect(SDCardWalSyncImpl.markerEpochPlausible(raw, now: now), deviceCaptureTimePlausible(raw, seconds));
    }
  });
}
