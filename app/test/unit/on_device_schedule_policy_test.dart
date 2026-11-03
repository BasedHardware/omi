import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';

void main() {
  const policy = OnDeviceSchedulePolicy(
    interval: Duration(hours: 3),
    minBatteryPercent: 30,
    criticalBatteryPercent: 10,
  );
  final now = DateTime(2026, 10, 14, 12);

  OnDeviceRunDecision decide({
    OnDeviceSchedule schedule = OnDeviceSchedule.whileCharging,
    bool charging = false,
    int? battery = 80,
    Duration pending = const Duration(minutes: 30),
    DateTime? lastRunAt,
    bool transcribeNow = false,
  }) {
    return policy.decide(OnDeviceRunInputs(
      schedule: schedule,
      isCharging: charging,
      batteryPercent: battery,
      pendingAudio: pending,
      lastRunAt: lastRunAt,
      now: now,
      transcribeNowRequested: transcribeNow,
    ));
  }

  group('nothing pending', () {
    test('waits on every schedule, even on a charger or when asked', () {
      for (final schedule in OnDeviceSchedule.values) {
        expect(decide(schedule: schedule, pending: Duration.zero, charging: true, transcribeNow: true),
            const OnDeviceRunDecision.wait(OnDeviceRunReason.nothingPending));
      }
    });
  });

  group('charger', () {
    test('every schedule runs on a charger', () {
      for (final schedule in OnDeviceSchedule.values) {
        expect(decide(schedule: schedule, charging: true, battery: 5),
            const OnDeviceRunDecision.run(OnDeviceRunReason.charging));
      }
    });

    test('a Transcribe Now tap on a charger reports the request', () {
      expect(
          decide(charging: true, transcribeNow: true), const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested));
    });
  });

  group('while charging', () {
    test('waits on battery', () {
      expect(decide(), const OnDeviceRunDecision.wait(OnDeviceRunReason.waitingForCharger));
    });

    test('Transcribe Now runs on battery', () {
      expect(decide(transcribeNow: true), const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested));
    });

    test('Transcribe Now still runs at the minimum used for scheduled work', () {
      expect(decide(transcribeNow: true, battery: 15), const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested));
    });

    test('Transcribe Now waits below the critical level', () {
      expect(decide(transcribeNow: true, battery: 9), const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow));
    });
  });

  group('every few hours', () {
    const schedule = OnDeviceSchedule.everyFewHours;

    test('runs when it never ran', () {
      expect(decide(schedule: schedule), const OnDeviceRunDecision.run(OnDeviceRunReason.intervalElapsed));
    });

    test('runs once the interval has passed, exactly at the boundary', () {
      expect(decide(schedule: schedule, lastRunAt: now.subtract(const Duration(hours: 3))),
          const OnDeviceRunDecision.run(OnDeviceRunReason.intervalElapsed));
    });

    test('waits inside the interval and says when to look again', () {
      final last = now.subtract(const Duration(hours: 1));
      expect(
        decide(schedule: schedule, lastRunAt: last),
        OnDeviceRunDecision.wait(OnDeviceRunReason.waitingForInterval, retryAt: last.add(const Duration(hours: 3))),
      );
    });

    test('waits for a charger when the battery is low, even when due', () {
      expect(decide(schedule: schedule, battery: 29), const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow));
    });

    test('runs at exactly the minimum battery', () {
      expect(decide(schedule: schedule, battery: 30), const OnDeviceRunDecision.run(OnDeviceRunReason.intervalElapsed));
    });

    test('Transcribe Now skips the interval', () {
      expect(decide(schedule: schedule, lastRunAt: now, transcribeNow: true),
          const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested));
    });
  });

  group('as you talk', () {
    const schedule = OnDeviceSchedule.asYouTalk;

    test('runs continuously on battery', () {
      expect(decide(schedule: schedule, lastRunAt: now), const OnDeviceRunDecision.run(OnDeviceRunReason.continuous));
    });

    test('waits for a charger when the battery is low', () {
      expect(decide(schedule: schedule, battery: 20), const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow));
    });
  });

  test('an unknown battery level does not block scheduled work', () {
    expect(decide(schedule: OnDeviceSchedule.asYouTalk, battery: null),
        const OnDeviceRunDecision.run(OnDeviceRunReason.continuous));
    expect(decide(transcribeNow: true, battery: null), const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested));
  });
}
