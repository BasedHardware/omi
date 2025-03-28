import 'package:flutter/foundation.dart';

enum ExecutionTarget { web, android, ios, macOS, windows, linux }

class ExecutionGuard {
  static ExecutionTarget? currentTarget;

  ExecutionGuard() {
    currentTarget ??= currentPlatform;
  }

  dynamic notAllowedOn(List<ExecutionTarget> notAllowedOn, dynamic code) {
    currentTarget ??= currentPlatform;
    if (notAllowedOn.contains(currentTarget)) return;
    return code;
  }

  dynamic allowedOn(List<ExecutionTarget> allowedOn, dynamic code) {
    currentTarget ??= currentPlatform;
    if (allowedOn.contains(currentTarget)) return code;
    return;
  }

  static bool get isWeb => (currentTarget ??= currentPlatform) == ExecutionTarget.web;
  static bool get isAndroid => (currentTarget ??= currentPlatform) == ExecutionTarget.android;
  static bool get isIOS => (currentTarget ??= currentPlatform) == ExecutionTarget.ios;
  static bool get isMacOS => (currentTarget ??= currentPlatform) == ExecutionTarget.macOS;
  static bool get isWindows => (currentTarget ??= currentPlatform) == ExecutionTarget.windows;
  static bool get isLinux => (currentTarget ??= currentPlatform) == ExecutionTarget.linux;

  static ExecutionTarget get currentPlatform {
    if (kIsWeb) return ExecutionTarget.web;
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return ExecutionTarget.android;
      case TargetPlatform.iOS:
        return ExecutionTarget.ios;
      case TargetPlatform.windows:
        return ExecutionTarget.windows;
      case TargetPlatform.macOS:
        return ExecutionTarget.macOS;
      default:
        return ExecutionTarget.linux;
    }
  }
}
