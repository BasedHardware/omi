import 'package:flutter/material.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

/// Legacy context-free adapter over [OmiFeedback], for providers and services that only have the
/// global navigator. Code with a `BuildContext` calls `OmiFeedback` directly.
///
/// Timings follow [OmiFeedbackTiming]; the old per-call `color` and `duration` arguments are
/// accepted for source compatibility and ignored, so every toast looks and lasts the same.
class AppSnackbar {
  static BuildContext? get _context => globalNavigatorKey.currentState?.context;

  /// Informational toast (4 s).
  static void showSnackbar(String message, {Color? color, Duration? duration}) {
    final context = _context;
    if (context == null) return;
    OmiFeedback.info(context, message);
  }

  /// Error toast (8 s, with close).
  static void showSnackbarError(String message, {Duration? duration}) {
    final context = _context;
    if (context == null) return;
    OmiFeedback.error(context, message);
  }

  /// Confirmation toast (1.5 s).
  static void showSnackbarSuccess(String message, {Duration? duration}) {
    final context = _context;
    if (context == null) return;
    OmiFeedback.confirm(context, message);
  }
}
