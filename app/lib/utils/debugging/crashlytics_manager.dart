import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';

class CrashlyticsManager {
  static final CrashlyticsManager _instance = CrashlyticsManager._internal();
  static CrashlyticsManager get instance => _instance;

  CrashlyticsManager._internal();

  factory CrashlyticsManager() {
    return _instance;
  }

  static Future<void> init() async {
    // Disable Crashlytics collection in debug mode
    if (kDebugMode) {
      await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(false);
    } else {
      await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(true);
    }
  }

  void identifyUser(String email, String name, String userId) {
    if (!_deliverable) return;
    FirebaseCrashlytics.instance.setUserIdentifier(userId);
    if (email.isNotEmpty) {
      FirebaseCrashlytics.instance.setCustomKey('user_email', email);
    }
    if (name.isNotEmpty) {
      FirebaseCrashlytics.instance.setCustomKey('user_name', name);
    }
  }

  void logInfo(String message) {
    FirebaseCrashlytics.instance.log(message);
  }

  void logError(String message) {
    FirebaseCrashlytics.instance.log('ERROR: $message');
  }

  void logWarn(String message) {
    FirebaseCrashlytics.instance.log('WARN: $message');
  }

  void logDebug(String message) {
    FirebaseCrashlytics.instance.log('DEBUG: $message');
  }

  void logVerbose(String message) {
    FirebaseCrashlytics.instance.log('VERBOSE: $message');
  }

  /// No Firebase app means there is no Crashlytics to talk to (host test
  /// lane). Same guard main.dart's zone handler uses; without it the report
  /// throws [core/no-app] and masks the original error.
  static bool get _deliverable => Firebase.apps.isNotEmpty;

  void setUserAttribute(String key, String value) {
    if (!_deliverable) return;
    FirebaseCrashlytics.instance.setCustomKey(key, value);
  }

  void setEnabled(bool isEnabled) {
    if (!_deliverable) return;
    FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(isEnabled);
  }

  Future<void> reportCrash(
    Object exception,
    StackTrace stackTrace, {
    Map<String, String>? userAttributes,
  }) async {
    if (!_deliverable) return;
    if (userAttributes != null) {
      for (final entry in userAttributes.entries) {
        await FirebaseCrashlytics.instance.setCustomKey(entry.key, entry.value);
      }
    }
    await FirebaseCrashlytics.instance.recordError(exception, stackTrace);
  }

  NavigatorObserver? getNavigatorObserver() {
    return null;
  }

  bool get isSupported => true;
}
