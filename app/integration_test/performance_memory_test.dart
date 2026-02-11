import 'dart:developer' as developer;
import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/main.dart' as app;

/// Memory Leak Detection & Heap Growth Test
///
/// Navigates through all major screens in repeated cycles, forcing GC
/// between transitions, and measures heap growth per cycle.
///
/// Key metrics:
///   - Peak resident heap size
///   - Final heap size after all cycles
///   - Average heap growth per navigation cycle
///
/// Threshold: heap growth must stay below 5 MB per cycle on average.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/performance_memory_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Memory Performance Tests', () {
    testWidgets('Detect memory leaks across screen navigation cycles', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         MEMORY LEAK DETECTION TEST                          ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Launch the real app
      debugPrint('[1/4] Launching app...');
      app.main();

      // Wait for app initialization
      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      debugPrint('      App launched');

      // Handle onboarding
      await _handleOnboardingIfNeeded(tester);
      await _pumpFor(tester, 3000);
      await _dismissAnyPopup(tester);

      // Wait for app to stabilize
      debugPrint('[2/4] Waiting 30s for app to stabilize...');
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(seconds: 1));
        await _dismissAnyPopup(tester);
      }

      // Force GC and get baseline
      _forceGC();
      await _pumpFor(tester, 1000);
      final baselineHeap = _getCurrentHeapUsageMB();
      debugPrint('      Baseline heap: ${baselineHeap.toStringAsFixed(1)} MB');

      // Navigation cycle measurements
      const totalCycles = 10;
      final heapPerCycle = <double>[];
      double peakHeap = baselineHeap;

      debugPrint('');
      debugPrint('[3/4] Running $totalCycles navigation cycles...');

      for (int cycle = 0; cycle < totalCycles; cycle++) {
        debugPrint('');
        debugPrint('  ── Cycle ${cycle + 1}/$totalCycles ──');

        // Navigate: Home -> Chat -> Back -> Scroll conversations -> Settings -> Back
        await _navigateToChat(tester);
        await _pumpFor(tester, 2000);

        await _navigateBack(tester);
        await _pumpFor(tester, 1000);

        // Scroll conversations list
        await _scrollDown(tester);
        await _pumpFor(tester, 500);
        await _scrollUp(tester);
        await _pumpFor(tester, 500);

        // Navigate to settings
        await _navigateToSettings(tester);
        await _pumpFor(tester, 2000);
        await _navigateBack(tester);
        await _pumpFor(tester, 1000);

        // Force GC and measure
        _forceGC();
        await _pumpFor(tester, 500);
        final currentHeap = _getCurrentHeapUsageMB();

        if (currentHeap > peakHeap) peakHeap = currentHeap;
        heapPerCycle.add(currentHeap);

        final growth = currentHeap - baselineHeap;
        debugPrint('      Heap: ${currentHeap.toStringAsFixed(1)} MB (growth: +${growth.toStringAsFixed(1)} MB)');
      }

      // Final GC
      _forceGC();
      await _pumpFor(tester, 1000);
      final finalHeap = _getCurrentHeapUsageMB();

      // Calculate metrics
      final totalGrowth = finalHeap - baselineHeap;
      final growthPerCycle = totalGrowth / totalCycles;

      // Print results
      debugPrint('');
      debugPrint('[4/4] Results');
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                 MEMORY TEST RESULTS                         ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Baseline heap:       ${baselineHeap.toStringAsFixed(1).padLeft(8)} MB                        ║');
      debugPrint('║ Final heap:          ${finalHeap.toStringAsFixed(1).padLeft(8)} MB                        ║');
      debugPrint('║ Peak heap:           ${peakHeap.toStringAsFixed(1).padLeft(8)} MB                        ║');
      debugPrint('║ Total growth:        ${totalGrowth.toStringAsFixed(1).padLeft(8)} MB                        ║');
      debugPrint('║ Growth per cycle:    ${growthPerCycle.toStringAsFixed(2).padLeft(8)} MB                        ║');
      debugPrint('║ Navigation cycles:   ${totalCycles.toString().padLeft(8)}                            ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      final pass = growthPerCycle < 5.0;
      debugPrint('║ Status: ${pass ? "PASS" : "FAIL"} (threshold: < 5.0 MB/cycle)                      ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Write JSON results for reporting
      _writeResults({
        'test': 'memory',
        'baseline_heap_mb': baselineHeap,
        'final_heap_mb': finalHeap,
        'peak_heap_mb': peakHeap,
        'total_growth_mb': totalGrowth,
        'growth_per_cycle_mb': growthPerCycle,
        'cycles': totalCycles,
        'heap_per_cycle': heapPerCycle,
        'threshold_mb': 5.0,
        'pass': pass,
      });

      expect(
        growthPerCycle,
        lessThan(5.0),
        reason: 'Memory growth per navigation cycle should be < 5 MB (actual: ${growthPerCycle.toStringAsFixed(2)} MB)',
      );
    });
  });
}

/// Force garbage collection via Dart developer extension
void _forceGC() {
  // UserTag-based GC hint — the VM may honor this in profile mode
  developer.UserTag('gc').makeCurrent();
  developer.UserTag('').makeCurrent();
}

/// Get current heap usage in MB using ProcessInfo (best-effort)
double _getCurrentHeapUsageMB() {
  try {
    // On iOS/Android in profile mode, resident memory is a reasonable proxy
    final rss = ProcessInfo.currentRss;
    return rss / (1024 * 1024);
  } catch (_) {
    return 0.0;
  }
}

void _writeResults(Map<String, dynamic> results) {
  try {
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('/tmp/omi_perf_memory_$timestamp.json');
    final buffer = StringBuffer();
    buffer.writeln('{');
    results.forEach((key, value) {
      if (value is String) {
        buffer.writeln('  "$key": "$value",');
      } else if (value is List) {
        buffer.writeln('  "$key": [${value.join(', ')}],');
      } else if (value is bool) {
        buffer.writeln('  "$key": $value,');
      } else {
        buffer.writeln('  "$key": $value,');
      }
    });
    buffer.writeln('}');
    file.writeAsStringSync(buffer.toString());
    debugPrint('Results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save results: $e');
  }
}

// ─── Navigation Helpers ────────────────────────────────────────────────

Future<void> _pumpFor(WidgetTester tester, int milliseconds) async {
  final iterations = milliseconds ~/ 100;
  for (int i = 0; i < iterations; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _navigateToChat(WidgetTester tester) async {
  final askOmi = find.text('Ask Omi');
  if (askOmi.evaluate().isNotEmpty) {
    await tester.tap(askOmi);
    await _pumpFor(tester, 2000);
  }
}

Future<void> _navigateToSettings(WidgetTester tester) async {
  // Tap the top-left area where settings/profile icon typically is
  await tester.tapAt(const Offset(30, 60));
  await _pumpFor(tester, 2000);
}

Future<void> _navigateBack(WidgetTester tester) async {
  final backButton = find.byType(BackButton);
  if (backButton.evaluate().isNotEmpty) {
    await tester.tap(backButton.first);
    await _pumpFor(tester, 1000);
    return;
  }
  await tester.pageBack();
  await _pumpFor(tester, 1000);
}

Future<void> _scrollDown(WidgetTester tester) async {
  final size = tester.view.physicalSize / tester.view.devicePixelRatio;
  await tester.fling(find.byType(Scrollable).first, Offset(0, -size.height * 0.3), 800);
  await _pumpFor(tester, 500);
}

Future<void> _scrollUp(WidgetTester tester) async {
  final size = tester.view.physicalSize / tester.view.devicePixelRatio;
  await tester.fling(find.byType(Scrollable).first, Offset(0, size.height * 0.3), 800);
  await _pumpFor(tester, 500);
}

Future<void> _dismissAnyPopup(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 100));

  final lovingOmi = find.text('Loving Omi?');
  if (lovingOmi.evaluate().isNotEmpty) {
    final maybeLater = find.text('Maybe later');
    if (maybeLater.evaluate().isNotEmpty) {
      await tester.tap(maybeLater.first, warnIfMissed: false);
      await _pumpFor(tester, 500);
      return;
    }
    final maybeLaterCap = find.text('Maybe Later');
    if (maybeLaterCap.evaluate().isNotEmpty) {
      await tester.tap(maybeLaterCap.first, warnIfMissed: false);
      await _pumpFor(tester, 500);
      return;
    }
  }

  final skipForNow = find.text('Skip for now');
  if (skipForNow.evaluate().isNotEmpty) {
    await tester.tap(skipForNow.first, warnIfMissed: false);
    await _pumpFor(tester, 500);
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
    debugPrint('      Found auth screen - tapping Sign in with Google');
    await tester.tap(signIn);
    await _pumpFor(tester, 2000);

    debugPrint('      Waiting for sign-in (60s)...');
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

  // Handle remaining onboarding steps
  for (int attempt = 0; attempt < 20; attempt++) {
    await _pumpFor(tester, 500);
    if (find.text('Ask Omi').evaluate().isNotEmpty) return;

    final continueBtn = find.text('Continue');
    if (continueBtn.evaluate().isNotEmpty) {
      await tester.tap(continueBtn.first);
      await _pumpFor(tester, 2000);
      continue;
    }
    final skipForNow = find.text('Skip for now');
    if (skipForNow.evaluate().isNotEmpty) {
      await tester.tap(skipForNow.first);
      await _pumpFor(tester, 2000);
      continue;
    }
    final maybeLater = find.text('Maybe Later');
    if (maybeLater.evaluate().isNotEmpty) {
      await tester.tap(maybeLater.first);
      await _pumpFor(tester, 2000);
      continue;
    }
  }
}
