import 'dart:io';

import 'package:omi/backend/preferences.dart';

/// Client gate for S17 plan-authoritative on-device STT. Default off (dark).
///
/// Env wins so dogfood can flip without a settings write. Prefs default false
/// so today's Deepgram path stays until the flag is lit.
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
    return SharedPreferencesUtil().getBool(prefsKey);
  }

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
