import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

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

/// Uses the existing native UIDevice / BatteryManager snapshot channel.
abstract interface class PhonePowerSource {
  Future<PhonePowerState> read();
}

class NativePhonePowerSource implements PhonePowerSource {
  const NativePhonePowerSource();
  static const channel = MethodChannel('com.omi/phone_battery');
  @override
  Future<PhonePowerState> read() async {
    try {
      final data = await channel.invokeMapMethod<String, dynamic>('read');
      return PhonePowerState(
          isCharging: data?['battery_charging'] == true, batteryPercent: data?['battery_level'] as int?);
    } on PlatformException {
      return PhonePowerState.unknown;
    } on MissingPluginException {
      return PhonePowerState.unknown;
    }
  }
}

class UnknownPhonePowerSource implements PhonePowerSource {
  const UnknownPhonePowerSource();
  @override
  Future<PhonePowerState> read() async => PhonePowerState.unknown;
}
