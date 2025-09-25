import 'package:flutter/services.dart';

enum StartupBehavior {
  showMainWindow,
  showFloatingButton,
}

class AutoStartService {
  static const MethodChannel _channel = MethodChannel('com.omi.macos/autostart');

  static Future<bool> isAutoStartEnabled() async {
    try {
      return await _channel.invokeMethod('isAutoStartEnabled') ?? false;
    } on PlatformException catch (e) {
      print("Failed to get auto-start status: '${e.message}'.");
      return false;
    }
  }

  static Future<void> setAutoStart(bool isEnabled) async {
    try {
      await _channel.invokeMethod('setAutoStart', {'isEnabled': isEnabled});
    } on PlatformException catch (e) {
      print("Failed to set auto-start: '${e.message}'.");
    }
  }

  static Future<StartupBehavior> getStartupBehavior() async {
    try {
      final String behavior = await _channel.invokeMethod('getStartupBehavior') ?? 'showMainWindow';
      return StartupBehavior.values.firstWhere(
        (e) => e.toString().split('.').last == behavior,
        orElse: () => StartupBehavior.showMainWindow,
      );
    } on PlatformException catch (e) {
      print("Failed to get startup behavior: '${e.message}'.");
      return StartupBehavior.showMainWindow;
    }
  }

  static Future<void> setStartupBehavior(StartupBehavior behavior) async {
    try {
      await _channel.invokeMethod('setStartupBehavior', {'behavior': behavior.toString().split('.').last});
    } on PlatformException catch (e) {
      print("Failed to set startup behavior: '${e.message}'.");
    }
  }
}
