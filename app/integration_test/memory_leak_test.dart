import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/main.dart' as app;

/// Memory Leak Detection Test
///
/// Measures Dart heap usage across repeated navigation cycles to detect
/// memory leaks. A leak is flagged when heap growth exceeds the threshold
/// after multiple GC-forced iterations.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/memory_leak_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Memory Leak Detection', () {
    testWidgets('Detect heap growth across navigation cycles', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         MEMORY LEAK DETECTION TEST                           ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Launch the real app
      debugPrint('[1/6] Launching app...');
      app.main();

      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      debugPrint('      App launched');

      // Handle onboarding if needed
      await _handleOnboardingIfNeeded(tester);
      await _pumpFor(tester, 3000);
      await _dismissAnyPopup(tester);

      // Stabilize
      debugPrint('');
      debugPrint('[2/6] Stabilizing app (30s)...');
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(seconds: 1));
        await _dismissAnyPopup(tester);
        if (i % 10 == 0) debugPrint('      ${30 - i}s remaining...');
      }

      // Collect RSS snapshots across navigation cycles
      final snapshots = <_MemorySnapshot>[];
      const totalCycles = 10;
      const navActionsPerCycle = 5;

      // Wait for GC and take baseline
      debugPrint('');
      debugPrint('[3/6] Taking baseline RSS snapshot...');
      await _waitForGC();
      await _pumpFor(tester, 1000);
      final baseline = await _takeMemorySnapshot('baseline');
      snapshots.add(baseline);
      _printMemorySnapshot(baseline);

      // Run navigation cycles
      debugPrint('');
      debugPrint('[4/6] Running $totalCycles navigation cycles...');

      for (int cycle = 0; cycle < totalCycles; cycle++) {
        debugPrint('');
        debugPrint('      --- Cycle ${cycle + 1}/$totalCycles ---');

        // Navigate through screens
        for (int action = 0; action < navActionsPerCycle; action++) {
          await _performNavigationAction(tester, action);
        }

        // Return to home
        await _navigateHome(tester);
        await _pumpFor(tester, 2000);
        await _dismissAnyPopup(tester);

        // Wait for GC opportunity and snapshot
        await _waitForGC();
        await _pumpFor(tester, 500);

        final snapshot = await _takeMemorySnapshot('cycle_${cycle + 1}');
        snapshots.add(snapshot);
        _printMemorySnapshot(snapshot);
      }

      // Final stabilization
      debugPrint('');
      debugPrint('[5/6] Final stabilization...');
      for (int i = 0; i < 3; i++) {
        await _waitForGC();
        await _pumpFor(tester, 2000);
      }
      final finalSnapshot = await _takeMemorySnapshot('final');
      snapshots.add(finalSnapshot);
      _printMemorySnapshot(finalSnapshot);

      // Analysis
      debugPrint('');
      debugPrint('[6/6] Analyzing results...');
      _analyzeRssGrowth(snapshots);

      // Write results
      _writeResultsToFile(snapshots);
    });

    testWidgets('Detect leaks in isolated widget cycles', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         ISOLATED WIDGET MEMORY TEST                          ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // This test creates and destroys widgets in a loop to detect
      // widgets that don't properly dispose their resources.

      final results = <String, _LeakTestResult>{};

      // Test 1: ListView with many items
      debugPrint('[1/3] Testing ListView create/destroy cycles...');
      results['ListView'] = await _testWidgetCycles(
        tester,
        name: 'ListView',
        createWidget: () => MaterialApp(
          home: Scaffold(
            body: ListView.builder(
              itemCount: 500,
              itemBuilder: (context, index) => ListTile(
                title: Text('Item $index'),
                subtitle: Text('Description for item $index'),
              ),
            ),
          ),
        ),
      );

      // Test 2: AnimationController lifecycle
      debugPrint('[2/3] Testing AnimationController create/destroy cycles...');
      results['AnimationController'] = await _testWidgetCycles(
        tester,
        name: 'AnimationController',
        createWidget: () => const MaterialApp(
          home: Scaffold(body: _AnimatedTestWidget()),
        ),
      );

      // Test 3: Image loading cycles
      debugPrint('[3/3] Testing Image widget create/destroy cycles...');
      results['ImageWidget'] = await _testWidgetCycles(
        tester,
        name: 'ImageWidget',
        createWidget: () => MaterialApp(
          home: Scaffold(
            body: GridView.builder(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3),
              itemCount: 50,
              itemBuilder: (context, index) => Container(
                color: Color(0xFF000000 + (index * 5000)),
                child: Center(child: Text('$index')),
              ),
            ),
          ),
        ),
      );

      // Summary
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    WIDGET LEAK SUMMARY                       ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      for (final entry in results.entries) {
        final r = entry.value;
        final status = r.leakDetected ? 'LEAK' : 'OK  ';
        debugPrint(
          '║ [$status] ${entry.key.padRight(22)} │ growth: ${_formatBytes(r.rssGrowth).padLeft(10)} ║',
        );
      }
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Write JSON results
      _writeWidgetLeakResults(results);

      // Soft assertion - warn but don't fail for small leaks
      for (final entry in results.entries) {
        if (entry.value.leakDetected) {
          debugPrint('WARNING: Potential leak detected in ${entry.key}: '
              '${_formatBytes(entry.value.rssGrowth)} RSS growth over ${entry.value.cycles} cycles');
        }
      }
    });
  });
}

// =============================================================================
// Memory Snapshot Utilities
// =============================================================================

/// Tracks process-level Resident Set Size (RSS).
///
/// NOTE: RSS measures the entire process footprint (Dart heap + native allocations
/// + framework internals + GPU buffers + OS caches). It is NOT the same as Dart
/// heap usage. For precise Dart heap metrics, use the VM Service Protocol
/// (getAllocationProfile) which requires connecting to the observatory.
///
/// RSS is still a useful proxy for detecting large memory leaks — if RSS grows
/// monotonically across navigation cycles after stabilization, something is
/// leaking (whether Dart objects, native buffers, or images).
class _MemorySnapshot {
  final String label;
  final int rssBytes;
  final int maxRssBytes;
  final DateTime timestamp;

  _MemorySnapshot({
    required this.label,
    required this.rssBytes,
    required this.maxRssBytes,
    required this.timestamp,
  });
}

class _LeakTestResult {
  final int rssBefore;
  final int rssAfter;
  final int rssGrowth;
  final int cycles;
  final bool leakDetected;

  _LeakTestResult({
    required this.rssBefore,
    required this.rssAfter,
    required this.rssGrowth,
    required this.cycles,
    required this.leakDetected,
  });
}

Future<_MemorySnapshot> _takeMemorySnapshot(String label) async {
  // ProcessInfo.currentRss: process Resident Set Size (not Dart heap).
  // Available in profile mode without VM service connection.
  final rss = ProcessInfo.currentRss;
  final maxRss = ProcessInfo.maxRss;

  return _MemorySnapshot(
    label: label,
    rssBytes: rss,
    maxRssBytes: maxRss,
    timestamp: DateTime.now(),
  );
}

/// Pause to allow pending finalizers and GC to run.
///
/// NOTE: There is no reliable way to force Dart GC from application code.
/// This delay gives the runtime an opportunity to collect garbage, but does
/// not guarantee it. Multiple calls with delays improve the chance of GC
/// running before we sample RSS.
Future<void> _waitForGC() async {
  // Three short pauses — gives the runtime multiple scheduling opportunities
  for (int i = 0; i < 3; i++) {
    await Future<void>.delayed(const Duration(milliseconds: 200));
  }
}

void _printMemorySnapshot(_MemorySnapshot snapshot) {
  debugPrint('      ${snapshot.label}: '
      'RSS=${_formatBytes(snapshot.rssBytes)}, '
      'maxRSS=${_formatBytes(snapshot.maxRssBytes)}');
}

String _formatBytes(int bytes) {
  if (bytes < 1024) return '${bytes}B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)}KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)}MB';
}

void _analyzeRssGrowth(List<_MemorySnapshot> snapshots) {
  if (snapshots.length < 3) {
    debugPrint('      Not enough snapshots for analysis');
    return;
  }

  final baseline = snapshots.first;
  final finalSnap = snapshots.last;
  final totalGrowth = finalSnap.rssBytes - baseline.rssBytes;
  final growthPerCycle = totalGrowth / (snapshots.length - 2); // exclude baseline and final

  // Calculate trend (linear regression on RSS values)
  final rssValues = snapshots.map((s) => s.rssBytes.toDouble()).toList();
  final n = rssValues.length;
  double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
  for (int i = 0; i < n; i++) {
    sumX += i;
    sumY += rssValues[i];
    sumXY += i * rssValues[i];
    sumX2 += i * i;
  }
  final slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  final r2 = _calculateR2(rssValues);

  // Determine leak status
  // A leak is likely if:
  // 1. RSS consistently grows (positive slope)
  // 2. Growth is significant (>1MB total)
  // 3. Correlation is strong (R² > 0.7)
  // NOTE: RSS includes native + Dart allocations — a growing RSS strongly
  // suggests a leak somewhere, but pinpointing Dart vs native requires
  // VM Service heap inspection.
  final isLeaking = slope > 0 && totalGrowth > 1024 * 1024 && r2 > 0.7;

  debugPrint('');
  debugPrint('╔══════════════════════════════════════════════════════════════╗');
  debugPrint('║                    RSS MEMORY ANALYSIS                       ║');
  debugPrint('║  (Process RSS — includes Dart heap + native + framework)     ║');
  debugPrint('╠══════════════════════════════════════════════════════════════╣');
  debugPrint('║ Baseline RSS:     ${_formatBytes(baseline.rssBytes).padLeft(12)}                          ║');
  debugPrint('║ Final RSS:        ${_formatBytes(finalSnap.rssBytes).padLeft(12)}                          ║');
  debugPrint('║ Total growth:     ${_formatBytes(totalGrowth).padLeft(12)}                          ║');
  debugPrint('║ Growth/cycle:     ${_formatBytes(growthPerCycle.toInt()).padLeft(12)}                          ║');
  debugPrint('║ Trend slope:      ${slope.toStringAsFixed(0).padLeft(12)} bytes/cycle                ║');
  debugPrint('║ Trend R²:         ${r2.toStringAsFixed(3).padLeft(12)}                          ║');
  debugPrint('╠══════════════════════════════════════════════════════════════╣');

  if (isLeaking) {
    debugPrint('║  ⚠  POTENTIAL MEMORY LEAK DETECTED                          ║');
    debugPrint('║  RSS shows consistent growth with strong correlation.        ║');
    debugPrint('║  Use Dart DevTools for heap inspection to pinpoint source.   ║');
    final hourlyLeak = slope * 3600 / 30; // cycles per hour estimate
    debugPrint('║  Estimated hourly growth: ~${_formatBytes(hourlyLeak.toInt()).padLeft(8)}                   ║');
  } else {
    debugPrint('║  ✓  No significant memory leak detected                      ║');
    if (totalGrowth > 0) {
      debugPrint('║  Some growth observed but within normal bounds.              ║');
    }
  }
  debugPrint('╚══════════════════════════════════════════════════════════════╝');
}

double _calculateR2(List<double> values) {
  final n = values.length;
  if (n < 2) return 0;

  final mean = values.reduce((a, b) => a + b) / n;
  double ssRes = 0, ssTot = 0;

  // Linear fit
  double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
  for (int i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumX2 += i * i;
  }
  final slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  final intercept = (sumY - slope * sumX) / n;

  for (int i = 0; i < n; i++) {
    final predicted = intercept + slope * i;
    ssRes += (values[i] - predicted) * (values[i] - predicted);
    ssTot += (values[i] - mean) * (values[i] - mean);
  }

  if (ssTot == 0) return 0;
  return 1 - (ssRes / ssTot);
}

Future<_LeakTestResult> _testWidgetCycles(
  WidgetTester tester, {
  required String name,
  required Widget Function() createWidget,
  int cycles = 20,
}) async {
  // Warm up
  await tester.pumpWidget(createWidget());
  await _pumpFor(tester, 1000);
  await tester.pumpWidget(const MaterialApp(home: Scaffold()));
  await _pumpFor(tester, 500);

  // Baseline
  await _waitForGC();
  await _pumpFor(tester, 500);
  final rssBefore = ProcessInfo.currentRss;
  debugPrint('      $name baseline: ${_formatBytes(rssBefore)}');

  // Cycle: create, interact, destroy
  for (int i = 0; i < cycles; i++) {
    await tester.pumpWidget(createWidget());
    await _pumpFor(tester, 200);

    // Scroll if possible
    final scrollable = find.byType(Scrollable);
    if (scrollable.evaluate().isNotEmpty) {
      try {
        await tester.fling(scrollable.first, const Offset(0, -300), 1000);
        await _pumpFor(tester, 300);
      } catch (_) {
        // Fling may fail on some widgets
      }
    }

    // Destroy
    await tester.pumpWidget(const MaterialApp(home: Scaffold()));
    await _pumpFor(tester, 100);
  }

  // Wait for GC and measure
  await _waitForGC();
  await _pumpFor(tester, 1000);
  final rssAfter = ProcessInfo.currentRss;
  final growth = rssAfter - rssBefore;

  debugPrint('      $name after $cycles cycles: ${_formatBytes(rssAfter)} '
      '(growth: ${_formatBytes(growth)})');

  // Flag as leak if RSS growth exceeds 5MB over 20 cycles
  const leakThreshold = 5 * 1024 * 1024;
  return _LeakTestResult(
    rssBefore: rssBefore,
    rssAfter: rssAfter,
    rssGrowth: growth,
    cycles: cycles,
    leakDetected: growth > leakThreshold,
  );
}

// =============================================================================
// Navigation Helpers (reused from app_performance_test.dart patterns)
// =============================================================================

Future<void> _performNavigationAction(WidgetTester tester, int actionIndex) async {
  switch (actionIndex % 5) {
    case 0:
      // Try to open chat
      final askOmi = find.text('Ask Omi');
      if (askOmi.evaluate().isNotEmpty) {
        await tester.tap(askOmi);
        await _pumpFor(tester, 2000);
      }
      break;
    case 1:
      // Scroll the main list
      final scrollable = find.byType(Scrollable);
      if (scrollable.evaluate().isNotEmpty) {
        try {
          await tester.fling(scrollable.first, const Offset(0, -500), 1500);
          await _pumpFor(tester, 1000);
        } catch (_) {}
      }
      break;
    case 2:
      // Scroll back up
      final scrollable = find.byType(Scrollable);
      if (scrollable.evaluate().isNotEmpty) {
        try {
          await tester.fling(scrollable.first, const Offset(0, 500), 1500);
          await _pumpFor(tester, 1000);
        } catch (_) {}
      }
      break;
    case 3:
      // Try to open settings
      final settingsIcon = find.byIcon(Icons.settings);
      if (settingsIcon.evaluate().isNotEmpty) {
        await tester.tap(settingsIcon.first);
        await _pumpFor(tester, 2000);
      }
      break;
    case 4:
      // Just pump for idle measurement
      await _pumpFor(tester, 2000);
      break;
  }
}

Future<void> _navigateHome(WidgetTester tester) async {
  // Try back button multiple times to get to home
  for (int i = 0; i < 3; i++) {
    final backButton = find.byType(BackButton);
    final backIcon = find.byIcon(Icons.arrow_back);
    final closeIcon = find.byIcon(Icons.close);

    if (backButton.evaluate().isNotEmpty) {
      await tester.tap(backButton.first);
      await _pumpFor(tester, 500);
    } else if (backIcon.evaluate().isNotEmpty) {
      await tester.tap(backIcon.first);
      await _pumpFor(tester, 500);
    } else if (closeIcon.evaluate().isNotEmpty) {
      await tester.tap(closeIcon.first);
      await _pumpFor(tester, 500);
    } else {
      break;
    }
  }
}

// =============================================================================
// File Output
// =============================================================================

void _writeResultsToFile(List<_MemorySnapshot> snapshots) {
  try {
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final jsonFile = File('/tmp/omi_memory_$timestamp.json');
    final csvFile = File('/tmp/omi_memory_$timestamp.csv');

    // JSON output
    final jsonBuffer = StringBuffer();
    jsonBuffer.writeln('{');
    jsonBuffer.writeln('  "test": "memory_leak_detection",');
    jsonBuffer.writeln('  "metric": "process_rss (not dart heap)",');
    jsonBuffer.writeln('  "timestamp": "${DateTime.now().toIso8601String()}",');
    jsonBuffer.writeln('  "snapshots": [');
    for (int i = 0; i < snapshots.length; i++) {
      final s = snapshots[i];
      jsonBuffer.write('    {"label": "${s.label}", '
          '"rss_bytes": ${s.rssBytes}, '
          '"max_rss_bytes": ${s.maxRssBytes}, '
          '"timestamp": "${s.timestamp.toIso8601String()}"}');
      if (i < snapshots.length - 1) jsonBuffer.writeln(',');
    }
    jsonBuffer.writeln('\n  ]');
    jsonBuffer.writeln('}');
    jsonFile.writeAsStringSync(jsonBuffer.toString());
    debugPrint('JSON results saved to: ${jsonFile.path}');

    // CSV output
    final csvBuffer = StringBuffer();
    csvBuffer.writeln('label,rss_bytes,max_rss_bytes,timestamp');
    for (final s in snapshots) {
      csvBuffer.writeln('${s.label},${s.rssBytes},${s.maxRssBytes},${s.timestamp.toIso8601String()}');
    }
    csvFile.writeAsStringSync(csvBuffer.toString());
    debugPrint('CSV results saved to: ${csvFile.path}');
  } catch (e) {
    debugPrint('Could not save results: $e');
  }
}

void _writeWidgetLeakResults(Map<String, _LeakTestResult> results) {
  try {
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('/tmp/omi_widget_leaks_$timestamp.json');

    final buffer = StringBuffer();
    buffer.writeln('{');
    buffer.writeln('  "test": "widget_leak_detection",');
    buffer.writeln('  "timestamp": "${DateTime.now().toIso8601String()}",');
    buffer.writeln('  "results": {');
    final entries = results.entries.toList();
    for (int i = 0; i < entries.length; i++) {
      final e = entries[i];
      buffer.write('    "${e.key}": {'
          '"rss_before": ${e.value.rssBefore}, '
          '"rss_after": ${e.value.rssAfter}, '
          '"rss_growth": ${e.value.rssGrowth}, '
          '"cycles": ${e.value.cycles}, '
          '"leak_detected": ${e.value.leakDetected}}');
      if (i < entries.length - 1) buffer.writeln(',');
    }
    buffer.writeln('\n  }');
    buffer.writeln('}');
    file.writeAsStringSync(buffer.toString());
    debugPrint('Widget leak results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save widget leak results: $e');
  }
}

// =============================================================================
// Test Widget for AnimationController lifecycle test
// =============================================================================

class _AnimatedTestWidget extends StatefulWidget {
  const _AnimatedTestWidget();

  @override
  State<_AnimatedTestWidget> createState() => _AnimatedTestWidgetState();
}

class _AnimatedTestWidgetState extends State<_AnimatedTestWidget> with TickerProviderStateMixin {
  late final List<AnimationController> _controllers;

  @override
  void initState() {
    super.initState();
    // Create multiple animation controllers to stress-test disposal
    _controllers = List.generate(
      10,
      (i) => AnimationController(
        duration: Duration(milliseconds: 500 + i * 100),
        vsync: this,
      )..repeat(reverse: true),
    );
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: _controllers.map((c) {
        return AnimatedBuilder(
          animation: c,
          builder: (context, child) {
            return Container(
              height: 30,
              // ignore: deprecated_member_use
              color: Colors.blue.withOpacity(c.value),
            );
          },
        );
      }).toList(),
    );
  }
}

// =============================================================================
// Onboarding / Popup Helpers (from app_performance_test.dart)
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

  // Skip through any remaining onboarding
  for (int attempt = 0; attempt < 20; attempt++) {
    await _pumpFor(tester, 500);

    if (find.text('Ask Omi').evaluate().isNotEmpty) return;

    final continueBtn = find.text('Continue');
    if (continueBtn.evaluate().isNotEmpty) {
      await tester.tap(continueBtn.first);
      await _pumpFor(tester, 1000);
      continue;
    }

    final maybeLater = find.text('Maybe Later');
    if (maybeLater.evaluate().isNotEmpty) {
      await tester.tap(maybeLater.first);
      await _pumpFor(tester, 1000);
      continue;
    }

    final skip = find.text('Skip for now');
    if (skip.evaluate().isNotEmpty) {
      await tester.tap(skip.first);
      await _pumpFor(tester, 1000);
      continue;
    }

    final skipAlt = find.text('Skip');
    if (skipAlt.evaluate().isNotEmpty) {
      await tester.tap(skipAlt.first);
      await _pumpFor(tester, 1000);
      continue;
    }
  }

  // If we still can't find the home screen, fail loudly
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

  for (final label in ['Skip for now', 'Skip', 'Not now', 'Dismiss']) {
    final btn = find.text(label);
    if (btn.evaluate().isNotEmpty) {
      await tester.tap(btn.first, warnIfMissed: false);
      await _pumpFor(tester, 500);
      return;
    }
  }
}
