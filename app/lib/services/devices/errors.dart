import 'package:flutter/material.dart';

import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void logErrorMessage(String message, String deviceId) {
  Logger.debug('($deviceId) $message');
  PlatformManager.instance.crashReporter.reportCrash(Exception(message), StackTrace.current);
}

void logCommonErrorMessage(String message) {
  Logger.debug(message);
  PlatformManager.instance.crashReporter.reportCrash(Exception(message), StackTrace.current);
}

void logCrashMessage(String message, String deviceId, Object e, StackTrace stackTrace) {
  logErrorMessage('$message error: $e', deviceId);
  PlatformManager.instance.crashReporter.reportCrash(e, stackTrace);
}

void logServiceNotFoundError(String serviceName, String deviceId) {
  logErrorMessage('$serviceName service not found', deviceId);
}

void logCharacteristicNotFoundError(String characteristicName, String deviceId) {
  logErrorMessage('$characteristicName characteristic not found', deviceId);
}

void logSubscribeError(String characteristicName, String deviceId, Object e, StackTrace stackTrace) {
  logCrashMessage('$characteristicName characteristic set notify', deviceId, e, stackTrace);
}
