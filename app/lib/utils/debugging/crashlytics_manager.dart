import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

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

  void setUserAttribute(String key, String value) {
    FirebaseCrashlytics.instance.setCustomKey(key, value);
  }

  void setEnabled(bool isEnabled) {
    FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(isEnabled);
  }

  Future<void> reportCrash(Object exception, StackTrace stackTrace, {Map<String, String>? userAttributes}) async {
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
