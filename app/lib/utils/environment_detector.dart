import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class EnvironmentDetector {
  static const _channel = MethodChannel('com.omi/environment');
  static const bool isBuildForBetaRing = bool.fromEnvironment('OMI_BETA_RELEASE_RING');

  /// iOS identifies TestFlight at runtime; Android internal releases carry a
  /// compile-time identity.  Neither production store channel may opt in by a
  /// user preference, which keeps release-ring routing deterministic.
  static bool shouldUseBetaReleaseRing(bool isTestFlight, {bool? betaBuild}) {
    return isTestFlight || (betaBuild ?? isBuildForBetaRing);
  }

  static Future<bool> isTestFlight() async {
    if (!Platform.isIOS) return false;
    try {
      final bool result = await _channel.invokeMethod('isTestFlight');
      return result;
    } catch (e) {
      debugPrint('EnvironmentDetector: Failed to check TestFlight: $e');
      return false;
    }
  }
}
