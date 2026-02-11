import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Pump the widget tree in 100ms increments for the given duration.
Future<void> pumpFor(WidgetTester tester, int milliseconds) async {
  final iterations = milliseconds ~/ 100;
  for (int i = 0; i < iterations; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// Dismiss common popups (review prompt, skip buttons).
Future<void> dismissAnyPopup(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 100));
  if (find.text('Loving Omi?').evaluate().isNotEmpty) {
    for (final text in ['Maybe later', 'Maybe Later']) {
      final btn = find.text(text);
      if (btn.evaluate().isNotEmpty) {
        await tester.tap(btn.first, warnIfMissed: false);
        await pumpFor(tester, 500);
        return;
      }
    }
  }
  for (final text in ['Skip for now', 'Skip', 'Not now']) {
    final btn = find.text(text);
    if (btn.evaluate().isNotEmpty) {
      await tester.tap(btn.first, warnIfMissed: false);
      await pumpFor(tester, 500);
      return;
    }
  }
}

/// Handle onboarding flow if the app starts on the auth screen.
Future<void> handleOnboardingIfNeeded(WidgetTester tester) async {
  debugPrint('      Checking for onboarding...');
  if (find.text('Ask Omi').evaluate().isNotEmpty) {
    debugPrint('      Already on home screen');
    return;
  }

  final signIn = find.text('Sign in with Google');
  if (signIn.evaluate().isNotEmpty) {
    debugPrint('      Found auth screen');
    await tester.tap(signIn);
    await pumpFor(tester, 2000);
    debugPrint('      >>> Please complete sign-in on device <<<');
    for (int i = 0; i < 120; i++) {
      await tester.pump(const Duration(milliseconds: 500));
      if (find.text('Ask Omi').evaluate().isNotEmpty) return;
      final cont = find.text('Continue');
      if (cont.evaluate().isNotEmpty) {
        await tester.tap(cont.first);
        await pumpFor(tester, 2000);
      }
    }
  }

  for (int attempt = 0; attempt < 20; attempt++) {
    await pumpFor(tester, 500);
    if (find.text('Ask Omi').evaluate().isNotEmpty) return;
    for (final text in ['Continue', 'Skip for now', 'Maybe Later']) {
      final btn = find.text(text);
      if (btn.evaluate().isNotEmpty) {
        await tester.tap(btn.first);
        await pumpFor(tester, 2000);
        break;
      }
    }
  }
}

/// Write test results as JSON to the report directory.
///
/// Uses PERF_REPORT_DIR env var if set, otherwise falls back to /tmp.
void writeResults(String testName, Map<String, dynamic> results) {
  try {
    final reportDir = Platform.environment['PERF_REPORT_DIR'] ?? '/tmp';
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('$reportDir/omi_perf_${testName}_$timestamp.json');
    const encoder = JsonEncoder.withIndent('  ');
    file.writeAsStringSync(encoder.convert(results));
    debugPrint('Results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save results: $e');
  }
}
