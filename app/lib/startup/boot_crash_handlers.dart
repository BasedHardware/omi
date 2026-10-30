import 'dart:ui';

import 'package:flutter/foundation.dart';

import 'package:omi/env/physical_qualification.dart';

/// Installs both handlers before running Crashlytics initialization, so an
/// initialization failure is also caught by the platform dispatcher.
class BootCrashHandlers {
  static Future<void> install({
    required Future<void> Function() initialize,
    required FlutterExceptionHandler flutterError,
    required ErrorCallback platformError,
  }) async {
    FlutterError.onError = flutterError;
    PlatformDispatcher.instance.onError = platformError;
    await PhysicalQualification.startupStage('crash_reporter', initialize);
  }
}
