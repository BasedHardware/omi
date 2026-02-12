import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/main.dart' as app;

import 'test_helpers.dart';

/// CPU Load Profiling Test
///
/// Measures CPU impact across different app states by counting frames
/// and measuring build/raster durations. More frames = more CPU work.
///
/// Test scenarios:
///   1. Idle (home screen, no interaction)
///   2. Active (scrolling conversations, chat animation)
///   3. Background simulation (no pumping — measures residual frame activity)
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/performance_cpu_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('CPU Performance Tests', () {
    testWidgets('Profile CPU load across app states', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         CPU LOAD PROFILING TEST                             ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Launch the real app
      debugPrint('[1/6] Launching app...');
      app.main();

      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      // Handle onboarding
      await handleOnboardingIfNeeded(tester);
      await pumpFor(tester, 3000);
      await dismissAnyPopup(tester);

      // Stabilize
      debugPrint('[2/6] Stabilizing (30s)...');
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(seconds: 1));
        await dismissAnyPopup(tester);
      }

      final allResults = <String, _CpuMetrics>{};

      // ── SCENARIO 1: Idle on home screen ──
      debugPrint('');
      debugPrint('[3/6] Profiling IDLE state (15s)...');
      debugPrint('      Home screen with no user interaction');

      var timings = <FrameTiming>[];
      void idleCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(idleCallback);

      for (int i = 0; i < 150; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(idleCallback);
      final idleMetrics = _calculateMetrics('Idle (Home)', timings, 15.0);
      allResults['idle'] = idleMetrics;
      _printMetrics(idleMetrics);

      // ── SCENARIO 2: Active scrolling ──
      debugPrint('');
      debugPrint('[4/6] Profiling ACTIVE state (15s)...');
      debugPrint('      Scrolling conversations list');

      timings = <FrameTiming>[];
      void activeCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(activeCallback);

      // Perform repeated scrolling during the measurement window
      for (int i = 0; i < 10; i++) {
        // Scroll down
        final scrollable = find.byType(Scrollable);
        if (scrollable.evaluate().isNotEmpty) {
          final size = tester.view.physicalSize / tester.view.devicePixelRatio;
          await tester.fling(scrollable.first, Offset(0, -size.height * 0.2), 600);
          await pumpFor(tester, 750);
          // Scroll back up
          await tester.fling(scrollable.first, Offset(0, size.height * 0.2), 600);
          await pumpFor(tester, 750);
        } else {
          await pumpFor(tester, 1500);
        }
      }

      WidgetsBinding.instance.removeTimingsCallback(activeCallback);
      final activeMetrics = _calculateMetrics('Active (Scroll)', timings, 15.0);
      allResults['active'] = activeMetrics;
      _printMetrics(activeMetrics);

      // ── SCENARIO 3: Chat screen (with animations) ──
      debugPrint('');
      debugPrint('[5/6] Profiling CHAT state (15s)...');
      debugPrint('      Chat screen with typing indicator animations');

      // Navigate to chat
      final askOmi = find.text('Ask Omi');
      if (askOmi.evaluate().isNotEmpty) {
        await tester.tap(askOmi);
        await pumpFor(tester, 2000);

        timings = <FrameTiming>[];
        void chatCallback(List<FrameTiming> t) => timings.addAll(t);
        WidgetsBinding.instance.addTimingsCallback(chatCallback);

        // Send a message to trigger typing indicator
        final textField = find.byType(TextField);
        if (textField.evaluate().isNotEmpty) {
          await tester.enterText(textField.first, 'hello');
          await pumpFor(tester, 500);
          final sendButton = find.byIcon(Icons.send);
          if (sendButton.evaluate().isNotEmpty) {
            await tester.tap(sendButton);
          } else {
            final altSend = find.byIcon(Icons.arrow_upward);
            if (altSend.evaluate().isNotEmpty) {
              await tester.tap(altSend);
            }
          }
        }

        // Profile for 15 seconds (includes typing indicator animation)
        for (int i = 0; i < 150; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }

        WidgetsBinding.instance.removeTimingsCallback(chatCallback);
        final chatMetrics = _calculateMetrics('Chat (Typing)', timings, 15.0);
        allResults['chat'] = chatMetrics;
        _printMetrics(chatMetrics);

        // Go back
        await tester.pageBack();
        await pumpFor(tester, 1000);
      } else {
        debugPrint('      Could not find Ask Omi button — skipping chat test');
      }

      // ── SCENARIO 4: Background simulation ──
      debugPrint('');
      debugPrint('[6/6] Profiling BACKGROUND state (10s)...');
      debugPrint('      Measuring residual frame activity');

      timings = <FrameTiming>[];
      void bgCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(bgCallback);

      // Only pump once per second — simulates minimal foreground activity
      for (int i = 0; i < 10; i++) {
        await tester.pump(const Duration(seconds: 1));
      }

      WidgetsBinding.instance.removeTimingsCallback(bgCallback);
      final bgMetrics = _calculateMetrics('Background', timings, 10.0);
      allResults['background'] = bgMetrics;
      _printMetrics(bgMetrics);

      // ── FINAL SUMMARY ──
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                  CPU PROFILING SUMMARY                      ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ State            │ Frames │ FPS    │ Avg Build │ Janky %    ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      for (final entry in allResults.entries) {
        final m = entry.value;
        debugPrint(
          '║ ${m.label.padRight(17)}│ ${m.totalFrames.toString().padLeft(6)} │ ${m.fps.toStringAsFixed(1).padLeft(6)} │ ${m.avgBuildMs.toStringAsFixed(2).padLeft(7)}ms │ ${m.jankyPercent.toStringAsFixed(1).padLeft(5)}%     ║',
        );
      }

      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Write JSON results
      final jsonResults = <String, dynamic>{
        'test': 'cpu',
        'scenarios': {
          for (final entry in allResults.entries)
            entry.key: {
              'label': entry.value.label,
              'total_frames': entry.value.totalFrames,
              'duration_seconds': entry.value.durationSeconds,
              'fps': double.parse(entry.value.fps.toStringAsFixed(2)),
              'avg_build_ms': double.parse(entry.value.avgBuildMs.toStringAsFixed(3)),
              'avg_raster_ms': double.parse(entry.value.avgRasterMs.toStringAsFixed(3)),
              'p95_build_ms': double.parse(entry.value.p95BuildMs.toStringAsFixed(3)),
              'peak_build_ms': double.parse(entry.value.peakBuildMs.toStringAsFixed(3)),
              'janky_frames': entry.value.jankyFrames,
              'janky_percent': double.parse(entry.value.jankyPercent.toStringAsFixed(2)),
            },
        },
      };
      writeResults('cpu', jsonResults);

      // Assertions
      final idle = allResults['idle']!;
      expect(idle.fps, lessThan(120), reason: 'Idle FPS should be reasonable (not spinning at max)');
    });
  });
}

class _CpuMetrics {
  final String label;
  final int totalFrames;
  final double durationSeconds;
  final double fps;
  final double avgBuildMs;
  final double avgRasterMs;
  final double p95BuildMs;
  final double peakBuildMs;
  final int jankyFrames;
  final double jankyPercent;

  _CpuMetrics({
    required this.label,
    required this.totalFrames,
    required this.durationSeconds,
    required this.fps,
    required this.avgBuildMs,
    required this.avgRasterMs,
    required this.p95BuildMs,
    required this.peakBuildMs,
    required this.jankyFrames,
    required this.jankyPercent,
  });
}

_CpuMetrics _calculateMetrics(String label, List<FrameTiming> timings, double durationSeconds) {
  if (timings.isEmpty) {
    return _CpuMetrics(
      label: label,
      totalFrames: 0,
      durationSeconds: durationSeconds,
      fps: 0,
      avgBuildMs: 0,
      avgRasterMs: 0,
      p95BuildMs: 0,
      peakBuildMs: 0,
      jankyFrames: 0,
      jankyPercent: 0,
    );
  }

  final buildUs = timings.map((t) => t.buildDuration.inMicroseconds).toList()..sort();
  final rasterUs = timings.map((t) => t.rasterDuration.inMicroseconds).toList()..sort();

  final avgBuild = buildUs.reduce((a, b) => a + b) / buildUs.length;
  final avgRaster = rasterUs.reduce((a, b) => a + b) / rasterUs.length;
  final p95Build = buildUs[(buildUs.length * 0.95).toInt()];

  final janky = timings.where((t) => t.buildDuration.inMilliseconds + t.rasterDuration.inMilliseconds > 16).length;

  return _CpuMetrics(
    label: label,
    totalFrames: timings.length,
    durationSeconds: durationSeconds,
    fps: timings.length / durationSeconds,
    avgBuildMs: avgBuild / 1000,
    avgRasterMs: avgRaster / 1000,
    p95BuildMs: p95Build / 1000,
    peakBuildMs: buildUs.last / 1000,
    jankyFrames: janky,
    jankyPercent: timings.isNotEmpty ? (janky / timings.length * 100) : 0,
  );
}

void _printMetrics(_CpuMetrics m) {
  debugPrint('      ┌─────────────────────────────────────');
  debugPrint('      │ ${m.label}');
  debugPrint('      ├─────────────────────────────────────');
  debugPrint('      │ Frames:      ${m.totalFrames.toString().padLeft(6)}');
  debugPrint('      │ FPS:         ${m.fps.toStringAsFixed(1).padLeft(6)}');
  debugPrint('      │ Avg build:   ${m.avgBuildMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Avg raster:  ${m.avgRasterMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ P95 build:   ${m.p95BuildMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Peak build:  ${m.peakBuildMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Janky:       ${m.jankyFrames.toString().padLeft(6)} (${m.jankyPercent.toStringAsFixed(1)}%)');
  debugPrint('      └─────────────────────────────────────');
}
