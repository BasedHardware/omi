import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';

/// Whether Home shows the Daily Recaps row. Off by default for everyone; Developer Settings turns
/// it on. Home re-reads it with [reload] when it mounts and rebuilds from [listenable] when it flips.
abstract final class HomeDailyRecapsSetting {
  static const prefKey = 'homeDailyRecapsEnabled';

  static final ValueNotifier<bool> _enabled = ValueNotifier(false);

  static ValueListenable<bool> get listenable => _enabled;

  static bool get enabled => SharedPreferencesUtil().getBool(prefKey);

  static set enabled(bool value) {
    _enabled.value = value;
    SharedPreferencesUtil().saveBool(prefKey, value);
  }

  /// Picks up the saved value for the signed-in account (launch, sign-in, sign-out).
  static void reload() => _enabled.value = enabled;
}
