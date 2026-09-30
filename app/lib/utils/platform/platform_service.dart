import 'package:omi/env/physical_qualification.dart';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// A utility class to handle platform-specific service availability.
/// The app targets mobile only (iOS/Android). Desktop lives in desktop/.
class PlatformService {
  static bool get isAndroid => Platform.isAndroid;
  static bool get isIOS => Platform.isIOS;
  static bool get isMobile => isAndroid || isIOS;
  static bool get isApple => isIOS;
  static bool get isAnalyticsSupported => !PhysicalQualification.enabled && !(kIsWeb);
  static bool get isIntercomSupported => !PhysicalQualification.enabled;
  static bool get isCrashlyticsSupported => !PhysicalQualification.enabled;

  /// iOS reports `Version 18.2 (Build 22C150)` (NSProcessInfo's version
  /// string, which always leads with `Version`), so the major version is the
  /// integer following that prefix. Splitting at `.` would capture
  /// `Version 18` and fail int.tryParse. Darwin `uname` strings (e.g.
  /// `Darwin Kernel Version 24.5.0...`) are deliberately NOT parsed: they
  /// also contain the word `Version`, but the following integer is the
  /// kernel major, not the iOS major (Darwin 21 is iOS 15), so treating it
  /// as the marketing version over-reports and lets devices pass gates like
  /// `isIOSAtLeast(16)`/`isIOSAtLeast(27)` they do not satisfy. Anchoring on
  /// the leading `Version` keeps those hosts unrecognized, and unrecognized
  /// formats fail closed to 0.
  static int iosMajorVersion(String operatingSystemVersion) {
    final match = RegExp(r'^Version (\d+)').firstMatch(operatingSystemVersion);
    return int.tryParse(match?.group(1) ?? '') ?? 0;
  }

  /// True when the running iOS major version is at least [minimum].
  /// Non-iOS hosts and unparsable versions report 0 and fail every gate.
  static bool isIOSAtLeast(int minimum) =>
      Platform.isIOS && iosMajorVersion(Platform.operatingSystemVersion) >= minimum;

  /// Execute a function only if the platform supports it
  static T? executeIfSupported<T>(
    bool isSupported,
    T Function() function, {
    T? fallback,
  }) {
    if (isSupported) {
      return function();
    }
    return fallback;
  }

  /// Execute a future function only if the platform supports it
  static Future<T?> executeIfSupportedAsync<T>(
    bool isSupported,
    Future<T> Function() function, {
    T? fallback,
  }) async {
    if (isSupported) {
      return await function();
    }
    return fallback;
  }
}
