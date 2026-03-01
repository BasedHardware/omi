import 'package:flutter/material.dart';

import 'package:shared_preferences/shared_preferences.dart';

class ThemeModeProvider extends ChangeNotifier {
  static const String _themeModeKey = 'app_theme_mode';

  ThemeMode _themeMode = ThemeMode.dark;
  bool _initialized = false;

  ThemeModeProvider() {
    _loadSavedThemeMode();
  }

  ThemeMode get themeMode => _themeMode;
  bool get isInitialized => _initialized;

  Future<void> _loadSavedThemeMode() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(_themeModeKey);
    if (value != null) {
      _themeMode = _fromString(value);
    }
    // Default stays ThemeMode.dark if nothing saved
    _initialized = true;
    notifyListeners();
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    _themeMode = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_themeModeKey, _toString(mode));
    notifyListeners();
  }

  static ThemeMode _fromString(String value) {
    switch (value) {
      case 'light':
        return ThemeMode.light;
      case 'system':
        return ThemeMode.system;
      default:
        return ThemeMode.dark;
    }
  }

  static String _toString(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.light:
        return 'light';
      case ThemeMode.system:
        return 'system';
      case ThemeMode.dark:
        return 'dark';
    }
  }

  static String getDisplayName(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.dark:
        return 'Dark';
      case ThemeMode.light:
        return 'Light';
      case ThemeMode.system:
        return 'System Default';
    }
  }
}
