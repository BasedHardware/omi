import 'dart:convert';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/battery_display_policy.dart';

/// Stuck Omi battery readings kept in SharedPreferences, per device: `{id: [percent, epochMs]}`.
/// Entries for devices that are no longer saved (forgotten) are dropped on read and write.
class PrefsBatteryStuckStore implements BatteryStuckStore {
  static const key = 'batteryStuckReadings';

  @override
  Map<String, (int, DateTime)> load() {
    try {
      final encoded = SharedPreferencesUtil().getString(key);
      if (encoded.isEmpty) return {};
      final saved = _savedIds();
      final decoded = jsonDecode(encoded) as Map<String, dynamic>;
      return {
        for (final entry in decoded.entries)
          if (saved.contains(entry.key.toUpperCase()) && entry.value is List && (entry.value as List).length == 2)
            entry.key: (
              (entry.value as List)[0] as int,
              DateTime.fromMillisecondsSinceEpoch((entry.value as List)[1] as int),
            ),
      };
    } catch (_) {
      return {};
    }
  }

  @override
  void save(Map<String, (int, DateTime)> readings) {
    try {
      final saved = _savedIds();
      SharedPreferencesUtil().saveString(
        key,
        jsonEncode({
          for (final entry in readings.entries)
            if (saved.contains(entry.key.toUpperCase()))
              entry.key: [entry.value.$1, entry.value.$2.millisecondsSinceEpoch],
        }),
      );
    } catch (_) {
      // Preferences unavailable (early startup or tests): the in-session rules still apply.
    }
  }

  static Set<String> _savedIds() => {
        for (final device in SharedPreferencesUtil().btDevices) device.id.toUpperCase(),
        SharedPreferencesUtil().btDevice.id.toUpperCase(),
      };
}
