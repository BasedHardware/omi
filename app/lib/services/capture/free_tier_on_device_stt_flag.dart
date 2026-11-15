import 'dart:io';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/free_tier_on_device_stt_gate.dart';

/// Client gate for plan-authoritative on-device STT (S17): once the server says a plan's cloud
/// minutes are spent (`transcription_allowance.mode == on_device`), the phone transcribes live.
///
/// Default on (David 2026-11-16). Operational kill switch: the PostHog flag
/// `mobile-free-tier-on-device-stt-disabled` set true turns it off on the next socket; false, missing, offline or an
/// error keeps it on. Lifecycle: ops_kill; owner: free-tier-on-device.
///
/// The env var and the prefs key remain local overrides for dogfood and tests: a truthy env
/// forces on; prefs set false forces off.
class FreeTierOnDeviceSttFlag {
  static const environmentKey = 'OMI_FREE_TIER_ON_DEVICE_STT';
  static const prefsKey = 'freeTierOnDeviceStt';

  static bool isEnabled({
    Map<String, String>? environment,
    bool? prefsOverride,
  }) {
    final env = environment ?? Platform.environment;
    if (isTruthy(env[environmentKey])) return true;
    if (prefsOverride != null) return prefsOverride;
    return SharedPreferencesUtil().getBool(prefsKey, defaultValue: true);
  }

  /// True when the remote kill switch [FreeTierOnDeviceSttGate.killSwitchFlag] is set.
  static Future<bool> killed({Future<bool> Function(String key)? readFlag, Future<bool> Function()? reloadFlags}) =>
      FreeTierOnDeviceSttGate.killed(readFlag: readFlag, reloadFlags: reloadFlags);

  static bool isTruthy(String? raw) {
    if (raw == null) return false;
    switch (raw.trim().toLowerCase()) {
      case '1':
      case 'true':
      case 'yes':
        return true;
      default:
        return false;
    }
  }
}
