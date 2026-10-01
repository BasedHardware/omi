import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';

Brightness resolveAppearanceBrightness(ThemeMode mode, Brightness systemBrightness) => switch (mode) {
      ThemeMode.light => Brightness.light,
      ThemeMode.dark => Brightness.dark,
      ThemeMode.system => systemBrightness,
    };

/// Persists the user's appearance choice. The app is light until someone picks Dark or System;
/// an unknown stored value is light too.
class AppearanceProvider extends ChangeNotifier {
  AppearanceProvider({String Function()? read, Future<void> Function(String)? write})
      : _read = read ?? (() => SharedPreferencesUtil().appearanceMode),
        _write = write ?? ((value) => SharedPreferencesUtil().setAppearanceMode(value)) {
    _mode = parse(_read());
  }

  final String Function() _read;
  final Future<void> Function(String) _write;
  late ThemeMode _mode;

  ThemeMode get mode => _mode;

  static ThemeMode parse(String? value) => switch (value) {
        'dark' => ThemeMode.dark,
        'system' => ThemeMode.system,
        _ => ThemeMode.light,
      };

  Future<void> setMode(ThemeMode mode) async {
    if (_mode == mode) return;
    _mode = mode;
    notifyListeners();
    await _write(mode.name);
  }
}
