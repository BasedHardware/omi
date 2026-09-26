import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/omi_appearance.dart';
import 'package:omi/ui/omi_tokens.dart';

/// Loads the saved Settings → Appearance choices (palette, haptics) and saves every later change
/// of the palette. Call once, right after [SharedPreferencesUtil.init].
void restoreAppearance() {
  final prefs = SharedPreferencesUtil();
  OmiAppearance.mode.value = OmiAppearanceMode.values.firstWhere(
    (mode) => mode.name == prefs.appearanceMode,
    orElse: () => OmiAppearanceMode.system,
  );
  OmiHaptics.enabled = prefs.hapticsEnabled;
  OmiAppearance.mode
    ..removeListener(_saveMode)
    ..addListener(_saveMode);
}

void _saveMode() => SharedPreferencesUtil().appearanceMode = OmiAppearance.mode.value.name;

/// Turns the app's haptics on or off and remembers the choice.
void setHapticsEnabled(bool enabled) {
  OmiHaptics.enabled = enabled;
  SharedPreferencesUtil().hapticsEnabled = enabled;
}
