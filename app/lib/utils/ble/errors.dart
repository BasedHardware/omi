import 'package:flutter/material.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

void logErrorMessage(String message, String deviceId) {
  debugPrint('($deviceId) $message');
  CrashReporting.reportHandledCrash(
    Exception(message),
    StackTrace.current,
    level: NonFatalExceptionLevel.error,
  );
}

void logCrashMessage(String message, String deviceId, Object e, StackTrace stackTrace) {
  logErrorMessage('$message error: $e', deviceId);
  CrashReporting.reportHandledCrash(
    e,
    stackTrace,
    level: NonFatalExceptionLevel.error,
    userAttributes: {'deviceId': deviceId},
  );
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
