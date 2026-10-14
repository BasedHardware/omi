import 'package:flutter/foundation.dart';

/// The phone's own power state (not the Omi device's battery).
@immutable
class PhonePowerState {
  const PhonePowerState({required this.isCharging, this.batteryPercent});

  static const unknown = PhonePowerState(isCharging: false);

  final bool isCharging;

  /// 0–100, or null when unknown.
  final int? batteryPercent;

  @override
  bool operator ==(Object other) =>
      other is PhonePowerState && other.isCharging == isCharging && other.batteryPercent == batteryPercent;

  @override
  int get hashCode => Object.hash(isCharging, batteryPercent);
}

/// Where the scheduling policy reads the phone's charging state and battery level.
///
/// The app has no phone-battery dependency yet, so production uses [UnknownPhonePowerSource]
/// (never charging, level unknown): "While charging" waits and nothing runs on its own. A platform
/// implementation lands with the transcription runner.
abstract interface class PhonePowerSource {
  Future<PhonePowerState> read();
}

class UnknownPhonePowerSource implements PhonePowerSource {
  const UnknownPhonePowerSource();

  @override
  Future<PhonePowerState> read() async => PhonePowerState.unknown;
}
