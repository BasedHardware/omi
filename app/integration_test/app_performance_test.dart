import 'dart:async';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/main.dart' as app;

/// Real App Animation Performance Profiling Test
///
/// This test handles onboarding automatically and profiles animation performance.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/app_performance_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Omi App Animation Performance', () {
    testWidgets('Profile all animation screens', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         OMI APP ANIMATION PERFORMANCE TEST                   ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Launch the real app
      debugPrint('[1/7] Launching app...');
      app.main();

      // Wait for app initialization - use pump() instead of pumpAndSettle()
      // because pumpAndSettle hangs on screens with continuous animations
      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      debugPrint('      App launched');

      // === HANDLE ONBOARDING IF PRESENT ===
      await _handleOnboardingIfNeeded(tester);

      // Wait for home screen to fully load
      await _pumpFor(tester, 3000);

      // Dismiss any popup that might appear (like "Loving Omi?" after home loads)
      await _dismissAnyPopup(tester);

      // Wait 60 seconds for app to stabilize before profiling
      debugPrint('');
      debugPrint('[2.5/7] Waiting 60 seconds for app to stabilize...');
      for (int i = 0; i < 60; i++) {
        await tester.pump(const Duration(seconds: 1));
        // Check and dismiss any popup that might appear during wait
        await _dismissAnyPopup(tester);
        if (i % 10 == 0) {
          debugPrint('      ${60 - i} seconds remaining...');
        }
      }
      debugPrint('      App stabilized');

      // Collect frame timing data
      final allFrameTimings = <String, List<FrameTiming>>{};
      List<FrameTiming> currentFrameTimings = [];

      void frameCallback(List<FrameTiming> timings) {
        currentFrameTimings.addAll(timings);
      }

      // === SCREEN 1: HOME (Conversations) ===
      debugPrint('');
      debugPrint('[3/7] Profiling HOME screen...');
      debugPrint('      (WaveformSection, ProcessingCapture animations)');

      currentFrameTimings = [];
      WidgetsBinding.instance.addTimingsCallback(frameCallback);

      // Profile home screen for 15 seconds
      for (int i = 0; i < 150; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(frameCallback);
      allFrameTimings['home'] = List.from(currentFrameTimings);
      _printScreenMetrics('HOME', currentFrameTimings);

      // === SCREEN 2: CHAT ===
      debugPrint('');
      debugPrint('[4/7] Navigating to CHAT screen...');

      // Find and tap the "Ask Omi" button
      final askOmiButton = find.text('Ask Omi');
      if (askOmiButton.evaluate().isNotEmpty) {
        await tester.tap(askOmiButton);
        await _pumpFor(tester, 2000);
        debugPrint('      Navigated to chat screen');

        debugPrint('');
        debugPrint('[5/7] Profiling CHAT screen...');
        debugPrint('      (TypingIndicator, VoiceRecorder animations)');

        currentFrameTimings = [];
        WidgetsBinding.instance.addTimingsCallback(frameCallback);

        // Profile chat screen for 15 seconds
        for (int i = 0; i < 150; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }

        WidgetsBinding.instance.removeTimingsCallback(frameCallback);
        allFrameTimings['chat'] = List.from(currentFrameTimings);
        _printScreenMetrics('CHAT', currentFrameTimings);

        // Try to trigger typing indicator by sending a message
        debugPrint('');
        debugPrint('[6/7] Triggering AI response...');

        final textField = find.byType(TextField);
        if (textField.evaluate().isNotEmpty) {
          await tester.enterText(textField.first, 'hello');
          await _pumpFor(tester, 500);

          // Find and tap send button
          final sendButton = find.byIcon(Icons.send);
          if (sendButton.evaluate().isNotEmpty) {
            await tester.tap(sendButton);
          } else {
            // Try arrow_upward icon (common send icon)
            final altSendButton = find.byIcon(Icons.arrow_upward);
            if (altSendButton.evaluate().isNotEmpty) {
              await tester.tap(altSendButton);
            }
          }
          await tester.pump();

          debugPrint('      Message sent, profiling typing indicator...');

          currentFrameTimings = [];
          WidgetsBinding.instance.addTimingsCallback(frameCallback);

          // Profile during AI response (10 seconds)
          for (int i = 0; i < 100; i++) {
            await tester.pump(const Duration(milliseconds: 100));
          }

          WidgetsBinding.instance.removeTimingsCallback(frameCallback);
          allFrameTimings['chat_typing'] = List.from(currentFrameTimings);
          _printScreenMetrics('CHAT (typing)', currentFrameTimings);
        }

        // Go back to home
        await tester.pageBack();
        await _pumpFor(tester, 1000);
      } else {
        debugPrint('      ⚠ Could not find Ask Omi button - skipping chat test');
      }

      // === FINAL SUMMARY ===
      debugPrint('');
      debugPrint('[7/7] Generating summary...');
      _printFinalSummary(allFrameTimings);
    });
  });
}

/// Pump frames for a specified duration (in milliseconds)
/// Use this instead of pumpAndSettle() for screens with continuous animations
Future<void> _pumpFor(WidgetTester tester, int milliseconds) async {
  final iterations = milliseconds ~/ 100;
  for (int i = 0; i < iterations; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// Handle onboarding flow if the app shows onboarding screens
/// Flow: Auth -> Name -> Primary Language -> Permissions -> User Review -> Speech Profile
Future<void> _handleOnboardingIfNeeded(WidgetTester tester) async {
  debugPrint('');
  debugPrint('[2/7] Checking for onboarding...');

  // Check if we're already on home screen
  final askOmi = find.text('Ask Omi');
  if (askOmi.evaluate().isNotEmpty) {
    debugPrint('      Already logged in - on home screen');
    return;
  }

  // Check for auth screen
  final signInWithGoogle = find.text('Sign in with Google');
  if (signInWithGoogle.evaluate().isNotEmpty) {
    debugPrint('      Found auth screen - starting onboarding flow');
    await _handleAuthFlow(tester);
    return;
  }

  // Check for "Get Started" button (welcome/splash screen)
  final getStarted = find.textContaining('Get Started');
  if (getStarted.evaluate().isNotEmpty) {
    debugPrint('      Found "Get Started" - tapping to proceed');
    await tester.tap(getStarted.first);
    await _pumpFor(tester, 2000);
    await _handleAuthFlow(tester);
    return;
  }

  // Check if we're on name screen
  final wantToGoBy = find.textContaining('Want to go by');
  if (wantToGoBy.evaluate().isNotEmpty) {
    debugPrint('      Found name screen - continuing from there');
    await _handleNameScreen(tester);
    await _handlePrimaryLanguageScreen(tester);
    await _handlePermissionsScreen(tester);
    await _handleUserReviewScreen(tester);
    await _handleSpeechProfileScreen(tester);
    return;
  }

  // Check if we're on primary language screen
  final primaryLanguage = find.textContaining('primary language');
  if (primaryLanguage.evaluate().isNotEmpty) {
    debugPrint('      Found primary language screen');
    await _handlePrimaryLanguageScreen(tester);
    await _handlePermissionsScreen(tester);
    await _handleUserReviewScreen(tester);
    await _handleSpeechProfileScreen(tester);
    return;
  }

  // Check if we're on permissions screen
  final grantPermissions = find.textContaining('Grant');
  if (grantPermissions.evaluate().isNotEmpty) {
    debugPrint('      Found permissions screen');
    await _handlePermissionsScreen(tester);
    await _handleUserReviewScreen(tester);
    await _handleSpeechProfileScreen(tester);
    return;
  }

  // Check if we're on user review screen (look for "Maybe Later" button)
  final maybeLater = find.text('Maybe Later');
  if (maybeLater.evaluate().isNotEmpty) {
    debugPrint('      Found user review screen');
    await _handleUserReviewScreen(tester);
    await _handleSpeechProfileScreen(tester);
    return;
  }

  debugPrint('      No onboarding detected - assuming logged in');
}

/// Handle the auth flow (Sign in with Google)
Future<void> _handleAuthFlow(WidgetTester tester) async {
  // Tap "Sign in with Google"
  final signInWithGoogle = find.text('Sign in with Google');
  if (signInWithGoogle.evaluate().isNotEmpty) {
    debugPrint('      Tapping "Sign in with Google"');
    await tester.tap(signInWithGoogle);
    await _pumpFor(tester, 2000);

    // Handle consent bottom sheet
    await _handleConsentSheet(tester);

    // Wait for Google sign-in to complete (user interaction required)
    debugPrint('      Waiting for Google sign-in (60 seconds)...');
    debugPrint('      >>> Please complete sign-in on device <<<');

    // Poll for next screen to appear
    for (int i = 0; i < 120; i++) {
      await tester.pump(const Duration(milliseconds: 500));

      // Check if we've reached home screen
      final askOmi = find.text('Ask Omi');
      if (askOmi.evaluate().isNotEmpty) {
        debugPrint('      Sign-in complete - reached home screen');
        return;
      }

      // Check if we're on the name screen
      final wantToGoBy = find.textContaining('Want to go by');
      if (wantToGoBy.evaluate().isNotEmpty) {
        debugPrint('      Sign-in complete - on name screen');
        await _handleNameScreen(tester);
        await _handlePrimaryLanguageScreen(tester);
        await _handlePermissionsScreen(tester);
        await _handleUserReviewScreen(tester);
        await _handleSpeechProfileScreen(tester);
        return;
      }
    }

    debugPrint('      ⚠ Sign-in timeout - continuing anyway');
  }
}

/// Handle consent bottom sheet (Continue with Google)
Future<void> _handleConsentSheet(WidgetTester tester) async {
  await _pumpFor(tester, 500);

  final continueWithGoogle = find.text('Continue with Google');
  if (continueWithGoogle.evaluate().isNotEmpty) {
    debugPrint('      Found consent sheet - tapping "Continue with Google"');
    await tester.tap(continueWithGoogle);
    await _pumpFor(tester, 2000);
  }
}

/// Handle name screen ("Want to go by something else?")
Future<void> _handleNameScreen(WidgetTester tester) async {
  debugPrint('      On name screen - tapping Continue');

  // Find and tap Continue button
  final continueBtn = find.text('Continue');
  if (continueBtn.evaluate().isNotEmpty) {
    await tester.tap(continueBtn.first);
    await _pumpFor(tester, 2000);
  }
}

/// Handle primary language screen ("What's your primary language?")
Future<void> _handlePrimaryLanguageScreen(WidgetTester tester) async {
  // Check if we're on the primary language screen
  final primaryLanguage = find.textContaining('primary language');
  if (primaryLanguage.evaluate().isEmpty) {
    debugPrint('      Not on primary language screen - skipping');
    return;
  }

  debugPrint('      On primary language screen - tapping Continue');

  // The language auto-selects from device locale, so Continue should be enabled
  // Just tap Continue
  final continueBtn = find.text('Continue');
  if (continueBtn.evaluate().isNotEmpty) {
    await tester.tap(continueBtn.first);
    await _pumpFor(tester, 2000);
  }
}

/// Handle permissions screen ("Grant permissions")
Future<void> _handlePermissionsScreen(WidgetTester tester) async {
  // Check if we're on the permissions screen
  final grantPermissions = find.textContaining('Grant');
  if (grantPermissions.evaluate().isEmpty) {
    debugPrint('      Not on permissions screen - skipping');
    return;
  }

  debugPrint('      On permissions screen - tapping Continue');

  // Tap Continue - this will trigger system permission dialogs
  final continueBtn = find.text('Continue');
  if (continueBtn.evaluate().isNotEmpty) {
    await tester.tap(continueBtn.first);
    await _pumpFor(tester, 3000); // Give more time for permission dialogs
  }
}

/// Handle user review screen ("Loving Omi?")
Future<void> _handleUserReviewScreen(WidgetTester tester) async {
  // Wait for screen to fully transition and check multiple times
  for (int attempt = 0; attempt < 10; attempt++) {
    await _pumpFor(tester, 500);

    // Check if we're on the user review screen by looking for "Maybe Later" button
    final maybeLater = find.text('Maybe Later');
    if (maybeLater.evaluate().isNotEmpty) {
      debugPrint('      On user review screen - tapping "Maybe Later"');
      await tester.tap(maybeLater.first);
      await _pumpFor(tester, 2000);
      return;
    }

    // Check if we've already passed to home screen
    final askOmi = find.text('Ask Omi');
    if (askOmi.evaluate().isNotEmpty) {
      debugPrint('      Already on home screen - skipping user review');
      return;
    }
  }

  debugPrint('      Not on user review screen - skipping');
}

/// Dismiss any popup that might appear during the test
/// This handles popups like "Loving Omi?" that can appear after reaching home
Future<void> _dismissAnyPopup(WidgetTester tester) async {
  // Pump frames to ensure UI is rendered
  await tester.pump(const Duration(milliseconds: 100));

  // First check if "Loving Omi?" text is visible - that's the popup title
  final lovingOmiTitle = find.text('Loving Omi?');
  if (lovingOmiTitle.evaluate().isNotEmpty) {
    debugPrint('      >>> POPUP DETECTED: "Loving Omi?" dialog is showing');

    // The app_review_service.dart uses lowercase 'Maybe later' (line 210)
    // Try to find and tap the TextButton with "Maybe later" text
    final maybeLater = find.text('Maybe later');
    if (maybeLater.evaluate().isNotEmpty) {
      debugPrint('      >>> Found "Maybe later" button - tapping to dismiss...');
      await tester.tap(maybeLater.first, warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));

      // Verify popup is gone
      if (find.text('Loving Omi?').evaluate().isEmpty) {
        debugPrint('      >>> Popup dismissed successfully!');
      } else {
        debugPrint('      >>> Popup still visible, trying again...');
        // Try tapping the TextButton widget directly
        final textButtons = find.byType(TextButton);
        if (textButtons.evaluate().length >= 1) {
          // The "Maybe later" is usually the last TextButton in the dialog
          await tester.tap(textButtons.last, warnIfMissed: false);
          await tester.pump(const Duration(milliseconds: 500));
          await tester.pump(const Duration(milliseconds: 500));
        }
      }
      return;
    }

    // Fallback: Try with capital L
    final maybeLaterCap = find.text('Maybe Later');
    if (maybeLaterCap.evaluate().isNotEmpty) {
      debugPrint('      >>> Found "Maybe Later" (capital) button - tapping...');
      await tester.tap(maybeLaterCap.first, warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      return;
    }

    // Last resort: tap any TextButton in the dialog
    final textButtons = find.byType(TextButton);
    if (textButtons.evaluate().isNotEmpty) {
      debugPrint('      >>> Tapping TextButton to dismiss popup...');
      await tester.tap(textButtons.last, warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      return;
    }
  }

  // Check for "Skip for now" (Speech profile popup)
  final skipForNow = find.text('Skip for now');
  if (skipForNow.evaluate().isNotEmpty) {
    debugPrint('      >>> Found "Skip for now" - TAPPING to dismiss');
    await tester.tap(skipForNow.first, warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    return;
  }

  // Check for generic "Skip" button
  final skip = find.text('Skip');
  if (skip.evaluate().isNotEmpty) {
    debugPrint('      >>> Found "Skip" - TAPPING to dismiss');
    await tester.tap(skip.first, warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    return;
  }

  // Check for "Not now" button
  final notNow = find.text('Not now');
  if (notNow.evaluate().isNotEmpty) {
    debugPrint('      >>> Found "Not now" - TAPPING to dismiss');
    await tester.tap(notNow.first, warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    return;
  }
}

/// Handle speech profile screen
Future<void> _handleSpeechProfileScreen(WidgetTester tester) async {
  // Wait for screen to fully transition and check multiple times
  for (int attempt = 0; attempt < 10; attempt++) {
    await _pumpFor(tester, 500);

    // Check if we're already on home screen
    final askOmi = find.text('Ask Omi');
    if (askOmi.evaluate().isNotEmpty) {
      debugPrint('      Onboarding complete - reached home screen');
      return;
    }

    // Check if we're on the speech profile screen - button text is "Skip for now"
    final skipForNowBtn = find.text('Skip for now');
    if (skipForNowBtn.evaluate().isNotEmpty) {
      debugPrint('      On speech profile screen - tapping "Skip for now"');
      await tester.tap(skipForNowBtn.first);
      await _pumpFor(tester, 2000);
      return;
    }

    // Also check for just "Skip" as fallback
    final skipBtn = find.text('Skip');
    if (skipBtn.evaluate().isNotEmpty) {
      debugPrint('      On speech profile screen - tapping Skip');
      await tester.tap(skipBtn.first);
      await _pumpFor(tester, 2000);
      return;
    }
  }

  debugPrint('      Not on speech profile screen - skipping');
}

void _printScreenMetrics(String screenName, List<FrameTiming> timings) {
  if (timings.isEmpty) {
    debugPrint('      ⚠ No frame timings collected for $screenName');
    return;
  }

  final buildTimes = timings.map((t) => t.buildDuration.inMicroseconds).toList()..sort();
  final rasterTimes = timings.map((t) => t.rasterDuration.inMicroseconds).toList()..sort();

  final avgBuild = buildTimes.reduce((a, b) => a + b) / buildTimes.length;
  final avgRaster = rasterTimes.reduce((a, b) => a + b) / rasterTimes.length;
  final p50Build = buildTimes[buildTimes.length ~/ 2];
  final p90Build = buildTimes[(buildTimes.length * 0.9).toInt()];
  final p99Build = buildTimes[(buildTimes.length * 0.99).toInt()];

  // Janky frames (>16ms total frame time)
  final jankyFrames =
      timings.where((t) => t.buildDuration.inMilliseconds + t.rasterDuration.inMilliseconds > 16).length;
  final jankyPercent = (jankyFrames / timings.length * 100);

  debugPrint('      ┌─────────────────────────────────────');
  debugPrint('      │ $screenName METRICS');
  debugPrint('      ├─────────────────────────────────────');
  debugPrint('      │ Frames:     ${timings.length.toString().padLeft(6)}');
  debugPrint('      │ Build avg:  ${(avgBuild / 1000).toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Build p50:  ${(p50Build / 1000).toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Build p90:  ${(p90Build / 1000).toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Build p99:  ${(p99Build / 1000).toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Raster avg: ${(avgRaster / 1000).toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Janky:      ${jankyFrames.toString().padLeft(6)} (${jankyPercent.toStringAsFixed(1)}%)');
  debugPrint('      └─────────────────────────────────────');
}

void _printFinalSummary(Map<String, List<FrameTiming>> allTimings) {
  debugPrint('');
  debugPrint('╔══════════════════════════════════════════════════════════════╗');
  debugPrint('║                    FINAL SUMMARY                             ║');
  debugPrint('╠══════════════════════════════════════════════════════════════╣');

  int totalFrames = 0;
  int totalJanky = 0;

  for (final entry in allTimings.entries) {
    final name = entry.key;
    final timings = entry.value;
    if (timings.isEmpty) continue;

    totalFrames += timings.length;

    final janky = timings.where((t) => t.buildDuration.inMilliseconds + t.rasterDuration.inMilliseconds > 16).length;
    totalJanky += janky;

    final jankyPct = (janky / timings.length * 100).toStringAsFixed(1);
    debugPrint(
        '║ ${name.padRight(15)} │ ${timings.length.toString().padLeft(5)} frames │ ${jankyPct.padLeft(5)}% janky      ║');
  }

  debugPrint('╠══════════════════════════════════════════════════════════════╣');

  final overallJankyPct = totalFrames > 0 ? (totalJanky / totalFrames * 100) : 0.0;
  debugPrint(
      '║ TOTAL           │ ${totalFrames.toString().padLeft(5)} frames │ ${overallJankyPct.toStringAsFixed(1).padLeft(5)}% janky      ║');
  debugPrint('╚══════════════════════════════════════════════════════════════╝');
  debugPrint('');

  // Write results to file for comparison
  _writeResultsToFile(allTimings);
}

void _writeResultsToFile(Map<String, List<FrameTiming>> allTimings) {
  try {
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('/tmp/omi_perf_$timestamp.csv');

    final buffer = StringBuffer();
    buffer.writeln('screen,frame_index,build_us,raster_us,total_us');

    for (final entry in allTimings.entries) {
      final screen = entry.key;
      for (var i = 0; i < entry.value.length; i++) {
        final timing = entry.value[i];
        final buildUs = timing.buildDuration.inMicroseconds;
        final rasterUs = timing.rasterDuration.inMicroseconds;
        buffer.writeln('$screen,$i,$buildUs,$rasterUs,${buildUs + rasterUs}');
      }
    }

    file.writeAsStringSync(buffer.toString());
    debugPrint('Results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save results to file: $e');
  }
}
