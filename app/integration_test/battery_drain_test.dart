import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/main.dart' as app;

/// Battery Drain Estimation Test
///
/// Measures CPU utilization and frame rendering costs over extended periods
/// to estimate battery impact. Profiles idle, active, and background-like states.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/battery_drain_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Battery Drain Estimation', () {
    testWidgets('Profile CPU and frame cost across app states', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         BATTERY DRAIN ESTIMATION TEST                        ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Launch app
      debugPrint('[1/8] Launching app...');
      app.main();
      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      debugPrint('      App launched');

      await _handleOnboardingIfNeeded(tester);
      await _pumpFor(tester, 3000);
      await _dismissAnyPopup(tester);

      // Stabilize
      debugPrint('');
      debugPrint('[2/8] Stabilizing (30s)...');
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(seconds: 1));
        await _dismissAnyPopup(tester);
        if (i % 10 == 0) debugPrint('      ${30 - i}s remaining...');
      }

      final stateResults = <_StateProfile>[];

      // === STATE 1: IDLE on Home Screen (60s) ===
      debugPrint('');
      debugPrint('[3/8] Profiling IDLE state (60s)...');
      debugPrint('      App on home screen, no user interaction');

      stateResults.add(await _profileState(
        tester,
        name: 'idle_home',
        durationSeconds: 60,
        interaction: null,
      ));

      // === STATE 2: ACTIVE SCROLLING (60s) ===
      debugPrint('');
      debugPrint('[4/8] Profiling ACTIVE SCROLLING state (60s)...');
      debugPrint('      Continuous scrolling through conversation list');

      stateResults.add(await _profileState(
        tester,
        name: 'active_scroll',
        durationSeconds: 60,
        interaction: (tester) async {
          final scrollable = find.byType(Scrollable);
          if (scrollable.evaluate().isNotEmpty) {
            try {
              await tester.fling(scrollable.first, const Offset(0, -300), 800);
            } catch (_) {}
          }
        },
        interactionInterval: 3,
      ));

      // === STATE 3: CHAT (typing indicator active) (60s) ===
      debugPrint('');
      debugPrint('[5/8] Profiling CHAT state (60s)...');

      final askOmi = find.text('Ask Omi');
      if (askOmi.evaluate().isNotEmpty) {
        await tester.tap(askOmi);
        await _pumpFor(tester, 2000);

        stateResults.add(await _profileState(
          tester,
          name: 'chat_screen',
          durationSeconds: 60,
          interaction: null,
        ));

        // Send a message to trigger typing indicator
        debugPrint('');
        debugPrint('[6/8] Profiling CHAT with typing indicator (60s)...');

        final textField = find.byType(TextField);
        if (textField.evaluate().isNotEmpty) {
          await tester.enterText(textField.first, 'Tell me about my recent conversations');
          await _pumpFor(tester, 500);

          final sendButton = find.byIcon(Icons.send);
          final altSend = find.byIcon(Icons.arrow_upward);
          if (sendButton.evaluate().isNotEmpty) {
            await tester.tap(sendButton);
          } else if (altSend.evaluate().isNotEmpty) {
            await tester.tap(altSend);
          }
          await tester.pump();

          stateResults.add(await _profileState(
            tester,
            name: 'chat_typing',
            durationSeconds: 60,
            interaction: null,
          ));
        }

        // Return to home
        await tester.pageBack();
        await _pumpFor(tester, 1000);
      } else {
        debugPrint('      Could not navigate to chat - skipping');
      }

      // === STATE 4: RAPID NAVIGATION (60s) ===
      debugPrint('');
      debugPrint('[7/8] Profiling RAPID NAVIGATION state (60s)...');
      debugPrint('      Rapidly switching between screens');

      stateResults.add(await _profileState(
        tester,
        name: 'rapid_nav',
        durationSeconds: 60,
        interaction: (tester) async {
          await _rapidNavCycle(tester);
        },
        interactionInterval: 5,
      ));

      // === SUMMARY ===
      debugPrint('');
      debugPrint('[8/8] Generating battery drain report...');
      _printBatteryReport(stateResults);
      await _writeResultsToFile(stateResults);
    });

    testWidgets('Measure frame rendering cost over time', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         FRAME RENDERING COST OVER TIME                       ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // This test measures whether frame cost increases over time
      // (indicating resource leaks or cache bloat).
      // NOTE: app.main() is NOT called here — both testWidgets in this file run in
      // the same process, so the app from the first test is still live. Calling
      // app.main() again would double-register Firebase, providers, and widget trees.

      await _pumpFor(tester, 3000);
      await _dismissAnyPopup(tester);

      // Stabilize
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(seconds: 1));
        await _dismissAnyPopup(tester);
      }

      // Take 10 measurements of 30 seconds each
      final measurements = <_FrameCostMeasurement>[];

      for (int round = 0; round < 10; round++) {
        debugPrint('');
        debugPrint('  Round ${round + 1}/10...');

        final timings = <FrameTiming>[];
        void callback(List<FrameTiming> t) => timings.addAll(t);

        WidgetsBinding.instance.addTimingsCallback(callback);

        // 30 seconds of activity
        for (int i = 0; i < 300; i++) {
          await tester.pump(const Duration(milliseconds: 100));

          // Occasional interaction
          if (i % 50 == 0) {
            final scrollable = find.byType(Scrollable);
            if (scrollable.evaluate().isNotEmpty) {
              try {
                await tester.fling(scrollable.first, const Offset(0, -200), 800);
              } catch (_) {}
            }
          }
        }

        WidgetsBinding.instance.removeTimingsCallback(callback);

        if (timings.isNotEmpty) {
          final buildTimes = timings.map((t) => t.buildDuration.inMicroseconds).toList()..sort();
          final rasterTimes = timings.map((t) => t.rasterDuration.inMicroseconds).toList()..sort();

          final measurement = _FrameCostMeasurement(
            round: round + 1,
            frameCount: timings.length,
            avgBuildUs: buildTimes.reduce((a, b) => a + b) / buildTimes.length,
            avgRasterUs: rasterTimes.reduce((a, b) => a + b) / rasterTimes.length,
            p99BuildUs: buildTimes[(buildTimes.length * 0.99).toInt()].toDouble(),
            p99RasterUs: rasterTimes[(rasterTimes.length * 0.99).toInt()].toDouble(),
            jankyFrames:
                timings.where((t) => t.buildDuration.inMilliseconds + t.rasterDuration.inMilliseconds > 16).length,
          );

          measurements.add(measurement);
          debugPrint('  Frames: ${measurement.frameCount}, '
              'Avg build: ${(measurement.avgBuildUs / 1000).toStringAsFixed(2)}ms, '
              'Janky: ${measurement.jankyFrames} (${(measurement.jankyFrames / measurement.frameCount * 100).toStringAsFixed(1)}%)');
        }
      }

      // Analyze trend
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    FRAME COST TREND                          ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Round │ Frames │ Build avg │ Raster avg │ p99 build │ Jank% ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      for (final m in measurements) {
        final jankPct = m.frameCount > 0 ? (m.jankyFrames / m.frameCount * 100) : 0.0;
        debugPrint(
          '║ ${m.round.toString().padLeft(5)} │ ${m.frameCount.toString().padLeft(6)} │ '
          '${(m.avgBuildUs / 1000).toStringAsFixed(2).padLeft(9)}ms │ '
          '${(m.avgRasterUs / 1000).toStringAsFixed(2).padLeft(10)}ms │ '
          '${(m.p99BuildUs / 1000).toStringAsFixed(2).padLeft(9)}ms │ '
          '${jankPct.toStringAsFixed(1).padLeft(5)}% ║',
        );
      }
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Check for degradation
      if (measurements.length >= 4) {
        final firstHalf = measurements.sublist(0, measurements.length ~/ 2);
        final secondHalf = measurements.sublist(measurements.length ~/ 2);

        final firstAvg = firstHalf.map((m) => m.avgBuildUs).reduce((a, b) => a + b) / firstHalf.length;
        final secondAvg = secondHalf.map((m) => m.avgBuildUs).reduce((a, b) => a + b) / secondHalf.length;
        final degradation = ((secondAvg - firstAvg) / firstAvg * 100);

        debugPrint('');
        if (degradation > 20) {
          debugPrint('⚠  Frame cost increased by ${degradation.toStringAsFixed(1)}% over test duration');
          debugPrint('   This suggests resource accumulation or cache bloat.');
        } else if (degradation > 0) {
          debugPrint('Frame cost change: +${degradation.toStringAsFixed(1)}% (within normal bounds)');
        } else {
          debugPrint('✓  Frame cost stable or improved (${degradation.toStringAsFixed(1)}% change)');
        }
      }

      // Write results
      await _writeFrameCostResults(measurements);
    });
  });
}

// =============================================================================
// State Profiling
// =============================================================================

class _StateProfile {
  final String name;
  final int durationSeconds;
  final int totalFrames;
  final double avgBuildMs;
  final double avgRasterMs;
  final double p50BuildMs;
  final double p90BuildMs;
  final double p99BuildMs;
  final int jankyFrames;
  final double framesPerSecond;

  _StateProfile({
    required this.name,
    required this.durationSeconds,
    required this.totalFrames,
    required this.avgBuildMs,
    required this.avgRasterMs,
    required this.p50BuildMs,
    required this.p90BuildMs,
    required this.p99BuildMs,
    required this.jankyFrames,
    required this.framesPerSecond,
  });

  double get jankyPercent => totalFrames > 0 ? jankyFrames / totalFrames * 100 : 0;

  /// Relative rendering cost: FPS * average frame time (ms).
  /// Higher = more GPU/CPU work per second = more battery drain.
  /// This is a RELATIVE metric for comparing app states against each other,
  /// NOT an absolute battery drain measurement. Actual mAh drain depends on
  /// device hardware, screen brightness, radios, etc.
  double get renderingCost {
    final avgFrameCostMs = avgBuildMs + avgRasterMs;
    return framesPerSecond * avgFrameCostMs;
  }
}

class _FrameCostMeasurement {
  final int round;
  final int frameCount;
  final double avgBuildUs;
  final double avgRasterUs;
  final double p99BuildUs;
  final double p99RasterUs;
  final int jankyFrames;

  _FrameCostMeasurement({
    required this.round,
    required this.frameCount,
    required this.avgBuildUs,
    required this.avgRasterUs,
    required this.p99BuildUs,
    required this.p99RasterUs,
    required this.jankyFrames,
  });
}

Future<_StateProfile> _profileState(
  WidgetTester tester, {
  required String name,
  required int durationSeconds,
  required Future<void> Function(WidgetTester)? interaction,
  int interactionInterval = 5,
}) async {
  final timings = <FrameTiming>[];
  void callback(List<FrameTiming> t) => timings.addAll(t);

  WidgetsBinding.instance.addTimingsCallback(callback);

  for (int sec = 0; sec < durationSeconds; sec++) {
    // 10 pumps per second
    for (int i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    // Periodic interaction
    if (interaction != null && sec % interactionInterval == 0) {
      await interaction(tester);
    }

    // Dismiss popups
    await _dismissAnyPopup(tester);

    if (sec % 15 == 0) {
      debugPrint('      $name: ${durationSeconds - sec}s remaining, '
          '${timings.length} frames collected');
    }
  }

  WidgetsBinding.instance.removeTimingsCallback(callback);

  if (timings.isEmpty) {
    debugPrint('      ⚠ No frames collected for $name');
    return _StateProfile(
      name: name,
      durationSeconds: durationSeconds,
      totalFrames: 0,
      avgBuildMs: 0,
      avgRasterMs: 0,
      p50BuildMs: 0,
      p90BuildMs: 0,
      p99BuildMs: 0,
      jankyFrames: 0,
      framesPerSecond: 0,
    );
  }

  final buildUs = timings.map((t) => t.buildDuration.inMicroseconds).toList()..sort();
  final rasterUs = timings.map((t) => t.rasterDuration.inMicroseconds).toList()..sort();

  final profile = _StateProfile(
    name: name,
    durationSeconds: durationSeconds,
    totalFrames: timings.length,
    avgBuildMs: buildUs.reduce((a, b) => a + b) / buildUs.length / 1000,
    avgRasterMs: rasterUs.reduce((a, b) => a + b) / rasterUs.length / 1000,
    p50BuildMs: buildUs[buildUs.length ~/ 2] / 1000,
    p90BuildMs: buildUs[(buildUs.length * 0.9).toInt()] / 1000,
    p99BuildMs: buildUs[(buildUs.length * 0.99).toInt()] / 1000,
    // 16ms = 60Hz budget. On 90/120Hz devices, frames between 8-16ms are also janky but won't be counted here.
    jankyFrames: timings.where((t) => t.buildDuration.inMilliseconds + t.rasterDuration.inMilliseconds > 16).length,
    framesPerSecond: timings.length / durationSeconds,
  );

  debugPrint('      ┌─────────────────────────────────────');
  debugPrint('      │ $name');
  debugPrint('      ├─────────────────────────────────────');
  debugPrint('      │ Frames:    ${profile.totalFrames} (${profile.framesPerSecond.toStringAsFixed(1)}/s)');
  debugPrint('      │ Build avg: ${profile.avgBuildMs.toStringAsFixed(2)}ms');
  debugPrint('      │ Build p90: ${profile.p90BuildMs.toStringAsFixed(2)}ms');
  debugPrint('      │ Build p99: ${profile.p99BuildMs.toStringAsFixed(2)}ms');
  debugPrint('      │ Raster:    ${profile.avgRasterMs.toStringAsFixed(2)}ms avg');
  debugPrint('      │ Janky:     ${profile.jankyFrames} (${profile.jankyPercent.toStringAsFixed(1)}%)');
  debugPrint('      │ Render cost: ${profile.renderingCost.toStringAsFixed(1)} (relative, higher=more drain)');
  debugPrint('      └─────────────────────────────────────');

  return profile;
}

// =============================================================================
// Report Generation
// =============================================================================

void _printBatteryReport(List<_StateProfile> states) {
  debugPrint('');
  debugPrint('╔══════════════════════════════════════════════════════════════╗');
  debugPrint('║                    BATTERY DRAIN REPORT                      ║');
  debugPrint('╠══════════════════════════════════════════════════════════════╣');
  debugPrint('║ State            │ FPS   │ Build avg │ Jank% │ Render cost ║');
  debugPrint('╠══════════════════════════════════════════════════════════════╣');

  for (final s in states) {
    debugPrint(
      '║ ${s.name.padRight(16)} │ ${s.framesPerSecond.toStringAsFixed(1).padLeft(5)} │ '
      '${s.avgBuildMs.toStringAsFixed(2).padLeft(7)}ms │ '
      '${s.jankyPercent.toStringAsFixed(1).padLeft(5)}% │ '
      '${s.renderingCost.toStringAsFixed(1).padLeft(8)}   ║',
    );
  }

  debugPrint('╠══════════════════════════════════════════════════════════════╣');

  // Find the worst offender
  if (states.isNotEmpty) {
    final worst = states.reduce((a, b) => a.renderingCost > b.renderingCost ? a : b);
    final best = states.reduce((a, b) => a.renderingCost < b.renderingCost ? a : b);

    debugPrint('║ Highest cost:  ${worst.name.padRight(40)}   ║');
    debugPrint('║ Lowest cost:   ${best.name.padRight(40)}   ║');

    if (worst.renderingCost > 0 && best.renderingCost > 0) {
      final ratio = worst.renderingCost / best.renderingCost;
      debugPrint('${'║ Cost ratio:    ${ratio.toStringAsFixed(1)}x'.padRight(61)}║');
    }
  }

  debugPrint('╚══════════════════════════════════════════════════════════════╝');

  // Recommendations
  debugPrint('');
  debugPrint('');
  debugPrint('Note: "Render cost" = FPS × avg frame time. It is a RELATIVE');
  debugPrint('metric for comparing states, not an absolute mAh measurement.');
  debugPrint('');
  debugPrint('Optimization recommendations:');
  for (final s in states) {
    if (s.jankyPercent > 10) {
      debugPrint('  ⚠ ${s.name}: ${s.jankyPercent.toStringAsFixed(1)}% janky frames — investigate heavy builds');
    }
    if (s.framesPerSecond > 30 && s.name.contains('idle')) {
      debugPrint('  ⚠ ${s.name}: ${s.framesPerSecond.toStringAsFixed(0)} FPS while idle — '
          'animations running unnecessarily');
    }
    if (s.p99BuildMs > 32) {
      debugPrint('  ⚠ ${s.name}: p99 build time ${s.p99BuildMs.toStringAsFixed(1)}ms — '
          'causes visible stuttering');
    }
  }
}

Future<void> _writeResultsToFile(List<_StateProfile> states) async {
  try {
    final dir = await getTemporaryDirectory();
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('${dir.path}/omi_battery_$timestamp.json');

    final buffer = StringBuffer();
    buffer.writeln('{');
    buffer.writeln('  "test": "battery_drain_estimation",');
    buffer.writeln('  "timestamp": "${DateTime.now().toIso8601String()}",');
    buffer.writeln('  "states": [');
    for (int i = 0; i < states.length; i++) {
      final s = states[i];
      buffer.write('    {"name": "${s.name}", '
          '"duration_seconds": ${s.durationSeconds}, '
          '"total_frames": ${s.totalFrames}, '
          '"fps": ${s.framesPerSecond.toStringAsFixed(2)}, '
          '"avg_build_ms": ${s.avgBuildMs.toStringAsFixed(3)}, '
          '"avg_raster_ms": ${s.avgRasterMs.toStringAsFixed(3)}, '
          '"p50_build_ms": ${s.p50BuildMs.toStringAsFixed(3)}, '
          '"p90_build_ms": ${s.p90BuildMs.toStringAsFixed(3)}, '
          '"p99_build_ms": ${s.p99BuildMs.toStringAsFixed(3)}, '
          '"janky_frames": ${s.jankyFrames}, '
          '"janky_percent": ${s.jankyPercent.toStringAsFixed(2)}, '
          '"rendering_cost_relative": ${s.renderingCost.toStringAsFixed(2)}}');
      if (i < states.length - 1) buffer.writeln(',');
    }
    buffer.writeln('\n  ]');
    buffer.writeln('}');
    file.writeAsStringSync(buffer.toString());
    debugPrint('Battery results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save results: $e');
  }
}

Future<void> _writeFrameCostResults(List<_FrameCostMeasurement> measurements) async {
  try {
    final dir = await getTemporaryDirectory();
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('${dir.path}/omi_frame_cost_$timestamp.json');

    final buffer = StringBuffer();
    buffer.writeln('{');
    buffer.writeln('  "test": "frame_cost_over_time",');
    buffer.writeln('  "timestamp": "${DateTime.now().toIso8601String()}",');
    buffer.writeln('  "measurements": [');
    for (int i = 0; i < measurements.length; i++) {
      final m = measurements[i];
      buffer.write('    {"round": ${m.round}, '
          '"frame_count": ${m.frameCount}, '
          '"avg_build_us": ${m.avgBuildUs.toStringAsFixed(1)}, '
          '"avg_raster_us": ${m.avgRasterUs.toStringAsFixed(1)}, '
          '"p99_build_us": ${m.p99BuildUs.toStringAsFixed(1)}, '
          '"p99_raster_us": ${m.p99RasterUs.toStringAsFixed(1)}, '
          '"janky_frames": ${m.jankyFrames}}');
      if (i < measurements.length - 1) buffer.writeln(',');
    }
    buffer.writeln('\n  ]');
    buffer.writeln('}');
    file.writeAsStringSync(buffer.toString());
    debugPrint('Frame cost results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save results: $e');
  }
}

// =============================================================================
// Navigation Helpers
// =============================================================================

Future<void> _rapidNavCycle(WidgetTester tester) async {
  // Try to open chat
  final askOmi = find.text('Ask Omi');
  if (askOmi.evaluate().isNotEmpty) {
    await tester.tap(askOmi);
    await _pumpFor(tester, 1000);
    await tester.pageBack();
    await _pumpFor(tester, 500);
  }

  // Try settings
  final settings = find.byIcon(Icons.settings);
  if (settings.evaluate().isNotEmpty) {
    await tester.tap(settings.first);
    await _pumpFor(tester, 1000);
    await tester.pageBack();
    await _pumpFor(tester, 500);
  }

  // Scroll
  final scrollable = find.byType(Scrollable);
  if (scrollable.evaluate().isNotEmpty) {
    try {
      await tester.fling(scrollable.first, const Offset(0, -400), 1200);
      await _pumpFor(tester, 500);
      await tester.fling(scrollable.first, const Offset(0, 400), 1200);
      await _pumpFor(tester, 500);
    } catch (_) {}
  }
}

// =============================================================================
// Onboarding / Popup Helpers
// =============================================================================

Future<void> _pumpFor(WidgetTester tester, int milliseconds) async {
  final iterations = milliseconds ~/ 100;
  for (int i = 0; i < iterations; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _handleOnboardingIfNeeded(WidgetTester tester) async {
  debugPrint('      Checking for onboarding...');

  final askOmi = find.text('Ask Omi');
  if (askOmi.evaluate().isNotEmpty) {
    debugPrint('      Already on home screen');
    return;
  }

  final signIn = find.text('Sign in with Google');
  if (signIn.evaluate().isNotEmpty) {
    debugPrint('      Auth screen detected - waiting for manual sign-in (60s)...');
    debugPrint('      >>> Please complete sign-in on device <<<');
    for (int i = 0; i < 120; i++) {
      await tester.pump(const Duration(milliseconds: 500));
      if (find.text('Ask Omi').evaluate().isNotEmpty) {
        debugPrint('      Sign-in complete');
        return;
      }
      final continueBtn = find.text('Continue');
      if (continueBtn.evaluate().isNotEmpty) {
        await tester.tap(continueBtn.first);
        await _pumpFor(tester, 2000);
      }
    }
  }

  for (int attempt = 0; attempt < 20; attempt++) {
    await _pumpFor(tester, 500);
    if (find.text('Ask Omi').evaluate().isNotEmpty) return;

    for (final label in ['Continue', 'Maybe Later', 'Skip for now', 'Skip']) {
      final btn = find.text(label);
      if (btn.evaluate().isNotEmpty) {
        await tester.tap(btn.first);
        await _pumpFor(tester, 1000);
        break;
      }
    }
  }

  // Fail loudly if we can't reach the home screen
  if (find.text('Ask Omi').evaluate().isEmpty) {
    debugPrint('');
    debugPrint('╔══════════════════════════════════════════════════════════════╗');
    debugPrint('║  ERROR: Could not reach home screen.                         ║');
    debugPrint('║  The app may be stuck on login/onboarding.                   ║');
    debugPrint('║  Performance data collected from this point will be invalid. ║');
    debugPrint('║                                                              ║');
    debugPrint('║  To fix: sign in on the device before running tests,         ║');
    debugPrint('║  or complete onboarding manually within the 60s window.      ║');
    debugPrint('╚══════════════════════════════════════════════════════════════╝');
    fail('Could not reach home screen — test results would be invalid. '
        'Please sign in on the device before running performance tests.');
  }
}

Future<void> _dismissAnyPopup(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 100));

  final lovingOmi = find.text('Loving Omi?');
  if (lovingOmi.evaluate().isNotEmpty) {
    for (final label in ['Maybe later', 'Maybe Later']) {
      final btn = find.text(label);
      if (btn.evaluate().isNotEmpty) {
        await tester.tap(btn.first, warnIfMissed: false);
        await _pumpFor(tester, 500);
        return;
      }
    }
  }

  for (final label in ['Skip for now', 'Skip', 'Not now', 'Dismiss']) {
    final btn = find.text(label);
    if (btn.evaluate().isNotEmpty) {
      await tester.tap(btn.first, warnIfMissed: false);
      await _pumpFor(tester, 500);
      return;
    }
  }
}
