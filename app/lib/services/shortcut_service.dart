import 'dart:io';

import 'package:flutter/services.dart';

class ShortcutInfo {
  final int keyCode;
  final int modifiers;
  final String displayString;

  ShortcutInfo({
    required this.keyCode,
    required this.modifiers,
    required this.displayString,
  });

  factory ShortcutInfo.fromMap(Map<String, dynamic> map) {
    return ShortcutInfo(
      keyCode: map['keyCode'] as int,
      modifiers: map['modifiers'] as int,
      displayString: map['displayString'] as String,
    );
  }
}

class ShortcutService {
  static const _channel = MethodChannel('com.omi/shortcuts');

  static bool get isSupported => Platform.isMacOS;

  // Callback for when native requests to open keyboard shortcuts page
  static Function? onOpenKeyboardShortcutsPage;

  static void initialize() {
    if (!isSupported) return;
    
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'openKeyboardShortcutsPage') {
        onOpenKeyboardShortcutsPage?.call();
      }
    });
  }

  static Future<ShortcutInfo?> getAskAIShortcut() async {
    if (!isSupported) return null;
    try {
      final result = await _channel.invokeMethod('getAskAIShortcut');
      return ShortcutInfo.fromMap(Map<String, dynamic>.from(result));
    } catch (e) {
      return null;
    }
  }

  static Future<ShortcutInfo?> getToggleControlBarShortcut() async {
    if (!isSupported) return null;
    try {
      final result = await _channel.invokeMethod('getToggleControlBarShortcut');
      return ShortcutInfo.fromMap(Map<String, dynamic>.from(result));
    } catch (e) {
      return null;
    }
  }

  static Future<bool> setAskAIShortcut(int keyCode, int modifiers) async {
    if (!isSupported) return false;
    try {
      final result = await _channel.invokeMethod('setAskAIShortcut', {
        'keyCode': keyCode,
        'modifiers': modifiers,
      });
      return result == true;
    } catch (e) {
      return false;
    }
  }

  static Future<bool> resetAskAIShortcut() async {
    if (!isSupported) return false;
    try {
      final result = await _channel.invokeMethod('resetAskAIShortcut');
      return result == true;
    } catch (e) {
      return false;
    }
  }

  static Future<bool> setToggleControlBarShortcut(int keyCode, int modifiers) async {
    if (!isSupported) return false;
    try {
      final result = await _channel.invokeMethod('setToggleControlBarShortcut', {
        'keyCode': keyCode,
        'modifiers': modifiers,
      });
      return result == true;
    } catch (e) {
      return false;
    }
  }

  static Future<bool> resetToggleControlBarShortcut() async {
    if (!isSupported) return false;
    try {
      final result = await _channel.invokeMethod('resetToggleControlBarShortcut');
      return result == true;
    } catch (e) {
      return false;
    }
  }

  static Future<bool> validateShortcut(int keyCode, int modifiers) async {
    if (!isSupported) return false;
    try {
      final result = await _channel.invokeMethod('validateShortcut', {
        'keyCode': keyCode,
        'modifiers': modifiers,
      });
      return result == true;
    } catch (e) {
      return false;
    }
  }
}
