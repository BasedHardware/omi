import 'package:flutter/foundation.dart';

import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_tuning.dart';

/// Why the policy decided to run or wait.
enum OnDeviceRunReason {
  /// Nothing is waiting to be transcribed.
  nothingPending,

  /// The reader tapped Transcribe Now.
  userRequested,

  /// The phone is on a charger; every schedule runs then.
  charging,

  /// "While charging" and the phone is on battery.
  waitingForCharger,

  /// "Every few hours" and the interval since the last run has passed.
  intervalElapsed,

  /// "Every few hours" and the last run was recent.
  waitingForInterval,

  /// "As you talk" runs continuously.
  continuous,

  /// The battery is too low to spend on transcription; waiting for a charger.
  batteryTooLow,
}

/// What the policy sees. Pure data: no clocks, plugins or prefs are read inside the policy.
@immutable
class OnDeviceRunInputs {
  const OnDeviceRunInputs({
    required this.schedule,
    required this.isCharging,
    required this.pendingAudio,
    required this.now,
    this.batteryPercent,
    this.lastRunAt,
    this.transcribeNowRequested = false,
  });

  final OnDeviceSchedule schedule;
  final bool isCharging;

  /// 0–100, or null when the platform does not report it.
  final int? batteryPercent;

  /// Audio recorded on this phone and not yet transcribed.
  final Duration pendingAudio;

  /// When the last on-device run finished, or null if it never ran.
  final DateTime? lastRunAt;

  final DateTime now;

  /// The reader asked to transcribe now, whatever the schedule.
  final bool transcribeNowRequested;
}

@immutable
class OnDeviceRunDecision {
  const OnDeviceRunDecision.run(this.reason)
      : shouldRun = true,
        retryAt = null;
  const OnDeviceRunDecision.wait(this.reason, {this.retryAt}) : shouldRun = false;

  final bool shouldRun;
  final OnDeviceRunReason reason;

  /// For a time-based wait, when the decision changes without any other input changing.
  final DateTime? retryAt;

  @override
  bool operator ==(Object other) =>
      other is OnDeviceRunDecision &&
      other.shouldRun == shouldRun &&
      other.reason == reason &&
      other.retryAt == retryAt;

  @override
  int get hashCode => Object.hash(shouldRun, reason, retryAt);

  @override
  String toString() => 'OnDeviceRunDecision(${shouldRun ? 'run' : 'wait'}, $reason, retryAt: $retryAt)';
}

/// Decides whether on-device transcription should run now.
///
/// A charger always wins: on power, every schedule runs. On battery, "While charging" waits,
/// "Every few hours" runs once per [interval] above [minBatteryPercent], and "As you talk" runs
/// above [minBatteryPercent]. Transcribe Now runs on battery down to [criticalBatteryPercent].
/// An unknown battery level is treated as enough: the platform, not the policy, protects a dying
/// phone.
class OnDeviceSchedulePolicy {
  const OnDeviceSchedulePolicy({
    this.interval = OnDeviceTuning.everyFewHoursInterval,
    this.minBatteryPercent = OnDeviceTuning.minBatteryPercentOnBattery,
    this.criticalBatteryPercent = OnDeviceTuning.criticalBatteryPercent,
  });

  final Duration interval;
  final int minBatteryPercent;
  final int criticalBatteryPercent;

  OnDeviceRunDecision decide(OnDeviceRunInputs inputs) {
    if (inputs.pendingAudio <= Duration.zero) {
      return const OnDeviceRunDecision.wait(OnDeviceRunReason.nothingPending);
    }
    if (inputs.isCharging) {
      return OnDeviceRunDecision.run(
          inputs.transcribeNowRequested ? OnDeviceRunReason.userRequested : OnDeviceRunReason.charging);
    }
    final battery = inputs.batteryPercent;
    if (inputs.transcribeNowRequested) {
      if (battery != null && battery < criticalBatteryPercent) {
        return const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow);
      }
      return const OnDeviceRunDecision.run(OnDeviceRunReason.userRequested);
    }
    switch (inputs.schedule) {
      case OnDeviceSchedule.whileCharging:
        return const OnDeviceRunDecision.wait(OnDeviceRunReason.waitingForCharger);
      case OnDeviceSchedule.everyFewHours:
        if (battery != null && battery < minBatteryPercent) {
          return const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow);
        }
        final last = inputs.lastRunAt;
        if (last == null) return const OnDeviceRunDecision.run(OnDeviceRunReason.intervalElapsed);
        final due = last.add(interval);
        if (!inputs.now.isBefore(due)) return const OnDeviceRunDecision.run(OnDeviceRunReason.intervalElapsed);
        return OnDeviceRunDecision.wait(OnDeviceRunReason.waitingForInterval, retryAt: due);
      case OnDeviceSchedule.asYouTalk:
        if (battery != null && battery < minBatteryPercent) {
          return const OnDeviceRunDecision.wait(OnDeviceRunReason.batteryTooLow);
        }
        return const OnDeviceRunDecision.run(OnDeviceRunReason.continuous);
    }
  }
}
