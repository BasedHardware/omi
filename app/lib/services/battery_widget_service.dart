import 'dart:io';

import 'package:flutter/services.dart';
import 'package:omi/utils/logger.dart';

/// Service that bridges device state from Flutter to the iOS lock screen WidgetKit extension.
///
/// Writes battery and mute state to shared App Group UserDefaults so the
/// lock screen widget can read it.
class BatteryWidgetService {
  static const _channel = MethodChannel('com.omi.battery_widget');

  static final BatteryWidgetService _instance = BatteryWidgetService._();
  factory BatteryWidgetService() => _instance;
  BatteryWidgetService._();

  /// Push the latest device battery info to the iOS widget.
  /// Note: mute state is managed separately via [updateMuteState] and is never
  /// overwritten by this call.
  Future<void> updateBatteryInfo({
    required String deviceName,
    required int batteryLevel,
    required String deviceType,
    required bool isConnected,
  }) async {
    if (!Platform.isIOS) return;
    try {
      await _channel.invokeMethod('updateBatteryInfo', {
        'deviceName': deviceName,
        'batteryLevel': batteryLevel,
        'deviceType': deviceType,
        'isConnected': isConnected,
      });
    } catch (e) {
      Logger.debug('BatteryWidgetService.updateBatteryInfo failed: $e');
    }
  }

  /// Update only the mute state without changing other widget data.
  Future<void> updateMuteState(bool isMuted) async {
    if (!Platform.isIOS) return;
    try {
      await _channel.invokeMethod('updateMuteState', {'isMuted': isMuted});
    } catch (e) {
      Logger.debug('BatteryWidgetService.updateMuteState failed: $e');
    }
  }
}
