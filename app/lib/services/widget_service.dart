import 'dart:io';

import 'package:flutter/services.dart';

class WidgetService {
  static const _channel = MethodChannel('com.omi.widget');

  static WidgetService? _instance;
  static WidgetService get instance {
    _instance ??= WidgetService._();
    return _instance!;
  }

  WidgetService._();

  Future<void> updateBatteryWidget({
    required int batteryLevel,
    required bool isConnected,
  }) async {
    if (!Platform.isIOS) return;
    try {
      await _channel.invokeMethod('updateBatteryWidget', {
        'batteryLevel': batteryLevel,
        'isConnected': isConnected,
      });
    } on PlatformException catch (_) {
      // Widget extension may not be available
    } on MissingPluginException catch (_) {
      // Method channel not set up on this platform
    }
  }
}
