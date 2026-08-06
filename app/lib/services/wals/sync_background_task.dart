import 'dart:io';

import 'package:flutter/services.dart';

import 'package:omi/utils/logger.dart';

/// iOS `beginBackgroundTask` bridge for the screen-lock sync grace (#7221).
///
/// No-ops on non-iOS. Failures are swallowed — grace still attempts work under
/// whatever suspension budget Flutter retains.
class SyncBackgroundTask {
  SyncBackgroundTask._();

  static const MethodChannel _channel = MethodChannel('com.omi/sync_background_task');

  static Future<void> begin() async {
    if (!Platform.isIOS) return;
    try {
      await _channel.invokeMethod<void>('begin');
    } catch (e) {
      Logger.debug('SyncBackgroundTask.begin failed: $e');
    }
  }

  static Future<void> end() async {
    if (!Platform.isIOS) return;
    try {
      await _channel.invokeMethod<void>('end');
    } catch (e) {
      Logger.debug('SyncBackgroundTask.end failed: $e');
    }
  }
}
