import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/main.dart' as app;

import 'test_helpers.dart';

/// Battery Drain Estimation Test
///
/// Measures battery level before and after a simulated usage session.
/// Uses platform channels to read battery level on iOS/Android.
///
/// Since battery drain is slow, this test runs a configurable-duration
/// usage pattern and estimates hourly drain rate.
///
/// Key metrics:
///   - Battery % at start and end
///   - Estimated drain rate per hour
///   - Total CPU frames during the session (proxy for energy use)
///
/// Note: For accurate battery measurement, run on a physical device
/// (not simulator). Simulator always reports 100% or -1.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/performance_battery_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Battery Performance Tests', () {
    testWidgets('Estimate battery drain during typical usage', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         BATTERY DRAIN ESTIMATION TEST                       ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Duration of the test session in minutes
      const sessionMinutes = 5;
      const sessionSeconds = sessionMinutes * 60;

      // Launch the real app
      debugPrint('[1/5] Launching app...');
      app.main();

      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      await handleOnboardingIfNeeded(tester);
      await pumpFor(tester, 3000);
      await dismissAnyPopup(tester);

      // Stabilize
      debugPrint('[2/5] Stabilizing (15s)...');
      for (int i = 0; i < 15; i++) {
        await tester.pump(const Duration(seconds: 1));
        await dismissAnyPopup(tester);
      }

      // Read initial battery level
      debugPrint('[3/5] Reading initial battery level...');
      final startBattery = await _getBatteryLevel();
      debugPrint('      Start battery: ${startBattery >= 0 ? "$startBattery%" : "unavailable (simulator?)"}');

      // Collect frame timings during the entire session
      final sessionTimings = <FrameTiming>[];
      void sessionCallback(List<FrameTiming> t) => sessionTimings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(sessionCallback);

      // ── Simulated usage pattern ──
      debugPrint('');
      debugPrint('[4/5] Running ${sessionMinutes}min simulated usage session...');

      final startTime = DateTime.now();
      int elapsed = 0;

      while (elapsed < sessionSeconds) {
        final remaining = sessionSeconds - elapsed;
        if (remaining % 60 == 0) {
          debugPrint('      ${(remaining / 60).ceil()} minutes remaining...');
        }

        // Alternate between different activities
        final activity = (elapsed ~/ 30) % 4; // Switch activity every 30s
        switch (activity) {
          case 0:
            // Idle viewing (home screen)
            for (int i = 0; i < 10 && elapsed < sessionSeconds; i++) {
              await tester.pump(const Duration(seconds: 1));
              elapsed++;
            }
            break;
          case 1:
            // Scrolling conversations
            final scrollable = find.byType(Scrollable);
            if (scrollable.evaluate().isNotEmpty) {
              final size = tester.view.physicalSize / tester.view.devicePixelRatio;
              await tester.fling(scrollable.first, Offset(0, -size.height * 0.2), 500);
              await pumpFor(tester, 2000);
              await tester.fling(scrollable.first, Offset(0, size.height * 0.2), 500);
              await pumpFor(tester, 2000);
            }
            for (int i = 0; i < 6 && elapsed < sessionSeconds; i++) {
              await tester.pump(const Duration(seconds: 1));
              elapsed++;
            }
            break;
          case 2:
            // Navigate to chat and back
            final askOmi = find.text('Ask Omi');
            if (askOmi.evaluate().isNotEmpty) {
              await tester.tap(askOmi);
              await pumpFor(tester, 2000);
              for (int i = 0; i < 5 && elapsed < sessionSeconds; i++) {
                await tester.pump(const Duration(seconds: 1));
                elapsed++;
              }
              await tester.pageBack();
              await pumpFor(tester, 1000);
            }
            for (int i = 0; i < 5 && elapsed < sessionSeconds; i++) {
              await tester.pump(const Duration(seconds: 1));
              elapsed++;
            }
            break;
          case 3:
            // Idle with popup dismissal
            for (int i = 0; i < 10 && elapsed < sessionSeconds; i++) {
              await tester.pump(const Duration(seconds: 1));
              await dismissAnyPopup(tester);
              elapsed++;
            }
            break;
        }
      }

      WidgetsBinding.instance.removeTimingsCallback(sessionCallback);

      // Read final battery level
      debugPrint('[5/5] Reading final battery level...');
      final endBattery = await _getBatteryLevel();
      debugPrint('      End battery: ${endBattery >= 0 ? "$endBattery%" : "unavailable"}');

      // Calculate metrics
      final actualDuration = DateTime.now().difference(startTime);
      final actualMinutes = actualDuration.inSeconds / 60.0;
      final batteryDrain = (startBattery >= 0 && endBattery >= 0) ? startBattery - endBattery : -1;
      final drainPerHour = batteryDrain >= 0 ? (batteryDrain / actualMinutes * 60) : -1.0;

      // Frame analysis (energy proxy)
      final totalFrames = sessionTimings.length;
      final fps = totalFrames / actualDuration.inSeconds;
      int jankyFrames = 0;
      if (sessionTimings.isNotEmpty) {
        jankyFrames = sessionTimings
            .where((t) => t.buildDuration.inMilliseconds + t.rasterDuration.inMilliseconds > 16)
            .length;
      }

      // Print results
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║               BATTERY TEST RESULTS                          ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Session duration:    ${actualMinutes.toStringAsFixed(1).padLeft(8)} min                       ║');
      debugPrint(
        '║ Start battery:       ${(startBattery >= 0 ? "$startBattery%" : "N/A").padLeft(8)}                           ║',
      );
      debugPrint(
        '║ End battery:         ${(endBattery >= 0 ? "$endBattery%" : "N/A").padLeft(8)}                           ║',
      );
      debugPrint(
        '║ Battery drain:       ${(batteryDrain >= 0 ? "$batteryDrain%" : "N/A").padLeft(8)}                           ║',
      );
      debugPrint(
        '║ Est. drain/hour:     ${(drainPerHour >= 0 ? "${drainPerHour.toStringAsFixed(1)}%" : "N/A").padLeft(8)}                           ║',
      );
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Total frames:        ${totalFrames.toString().padLeft(8)}                           ║');
      debugPrint('║ Avg FPS:             ${fps.toStringAsFixed(1).padLeft(8)}                           ║');
      debugPrint('║ Janky frames:        ${jankyFrames.toString().padLeft(8)}                           ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      if (drainPerHour >= 0) {
        final pass = drainPerHour < 10.0;
        debugPrint('║ Status: ${pass ? "PASS" : "FAIL"} (threshold: < 10%/hr)                         ║');
      } else {
        debugPrint('║ Status: SKIPPED (battery data unavailable — simulator?)    ║');
      }
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Write results
      writeResults('battery', {
        'test': 'battery',
        'session_minutes': actualMinutes,
        'start_battery': startBattery,
        'end_battery': endBattery,
        'battery_drain': batteryDrain,
        'drain_per_hour': drainPerHour,
        'total_frames': totalFrames,
        'avg_fps': fps,
        'janky_frames': jankyFrames,
        'threshold_drain_per_hour': 10.0,
        'pass': drainPerHour >= 0 ? drainPerHour < 10.0 : true,
      });

      // Only assert if battery data is available
      if (drainPerHour >= 0) {
        expect(
          drainPerHour,
          lessThan(10.0),
          reason: 'Battery drain should be < 10%/hr (actual: ${drainPerHour.toStringAsFixed(1)}%/hr)',
        );
      }
    });
  });
}

/// Read battery level using platform channel
/// Returns 0-100 for battery percentage, or -1 if unavailable
Future<int> _getBatteryLevel() async {
  try {
    const platform = MethodChannel('dev.flutter.pigeon.omi.BatteryChannel');
    final int result = await platform.invokeMethod('getBatteryLevel');
    return result;
  } catch (_) {
    // Fallback: try the standard device_info battery channel
    try {
      if (Platform.isAndroid) {
        const androidChannel = MethodChannel('plugins.flutter.io/battery');
        final int result = await androidChannel.invokeMethod('getBatteryLevel');
        return result;
      }
    } catch (_) {
      // Battery level not available (likely running on simulator)
    }
  }
  return -1;
}
