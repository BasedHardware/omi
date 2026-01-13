import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:omi/utils/logger.dart';

/// Flutter wrapper for the native Android ConnectionForegroundService.
///
/// This service runs in the foreground with `connectedDevice` service type,
/// which tells Android to prioritize keeping Bluetooth connections stable
/// even when the app is in the background.
class ConnectionForegroundService {
  static const _channel = MethodChannel('com.omi.connection_foreground_service');

  static final ConnectionForegroundService _instance = ConnectionForegroundService._();
  static ConnectionForegroundService get instance => _instance;

  ConnectionForegroundService._();

  bool _isRunning = false;

  /// Whether the service is currently running
  bool get isRunning => _isRunning;

  /// Start the foreground service to keep BLE connection alive
  Future<bool> start({String deviceName = 'Omi'}) async {
    if (!Platform.isAndroid) return true;

    try {
      final result = await _channel.invokeMethod('start', {
        'deviceName': deviceName,
      });
      _isRunning = result == true;
      Logger.debug('ConnectionForegroundService: started=$_isRunning');
      return _isRunning;
    } catch (e) {
      Logger.debug('ConnectionForegroundService: start failed: $e');
      return false;
    }
  }

  /// Stop the foreground service
  Future<bool> stop() async {
    if (!Platform.isAndroid) return true;

    try {
      final result = await _channel.invokeMethod('stop');
      _isRunning = false;
      Logger.debug('ConnectionForegroundService: stopped');
      return result == true;
    } catch (e) {
      Logger.debug('ConnectionForegroundService: stop failed: $e');
      return false;
    }
  }

  /// Check if the service is currently running
  Future<bool> checkIsRunning() async {
    if (!Platform.isAndroid) return false;

    try {
      final result = await _channel.invokeMethod('isRunning');
      _isRunning = result == true;
      return _isRunning;
    } catch (e) {
      Logger.debug('ConnectionForegroundService: checkIsRunning failed: $e');
      return false;
    }
  }

  /// Update the notification with device info
  Future<void> updateNotification({
    String deviceName = 'Omi',
    int? batteryLevel,
  }) async {
    if (!Platform.isAndroid) return;

    try {
      await _channel.invokeMethod('updateNotification', {
        'deviceName': deviceName,
        'batteryLevel': batteryLevel,
      });
    } catch (e) {
      Logger.debug('ConnectionForegroundService: updateNotification failed: $e');
    }
  }
}
