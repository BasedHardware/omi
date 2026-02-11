import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/main.dart' as app;

/// Responsiveness & Jank Detection Test
///
/// Profiles frame timings during common user interactions to detect jank.
///
/// Key metrics:
///   - Average frame time (build + raster)
///   - 95th percentile frame time
///   - Janky frame count (frames > 16ms = below 60fps target)
///   - Per-interaction breakdown
///
/// Extends the pattern from app_performance_test.dart with more granular
/// interaction-level measurements.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/performance_responsiveness_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Responsiveness Performance Tests', () {
    testWidgets('Profile frame timings during user interactions', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         RESPONSIVENESS & JANK DETECTION TEST                ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Launch app
      debugPrint('[1/7] Launching app...');
      app.main();

      for (int i = 0; i < 50; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      await _handleOnboardingIfNeeded(tester);
      await _pumpFor(tester, 3000);
      await _dismissAnyPopup(tester);

      // Stabilize
      debugPrint('[2/7] Stabilizing (30s)...');
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(seconds: 1));
        await _dismissAnyPopup(tester);
      }

      final allInteractions = <String, _InteractionMetrics>{};

      // ── INTERACTION 1: Conversation list scroll ──
      debugPrint('');
      debugPrint('[3/7] Profiling: Conversation list scroll...');

      var timings = <FrameTiming>[];
      void scrollCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(scrollCallback);

      for (int rep = 0; rep < 5; rep++) {
        final scrollable = find.byType(Scrollable);
        if (scrollable.evaluate().isNotEmpty) {
          final size = tester.view.physicalSize / tester.view.devicePixelRatio;
          await tester.fling(scrollable.first, Offset(0, -size.height * 0.3), 1000);
          await _pumpFor(tester, 1000);
          await tester.fling(scrollable.first, Offset(0, size.height * 0.3), 1000);
          await _pumpFor(tester, 1000);
        }
      }

      WidgetsBinding.instance.removeTimingsCallback(scrollCallback);
      final scrollMetrics = _calculateInteraction('List Scroll', timings);
      allInteractions['list_scroll'] = scrollMetrics;
      _printInteraction(scrollMetrics);

      // ── INTERACTION 2: Screen transition (Home -> Chat) ──
      debugPrint('');
      debugPrint('[4/7] Profiling: Home -> Chat transition...');

      timings = <FrameTiming>[];
      void transCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(transCallback);

      final askOmi = find.text('Ask Omi');
      if (askOmi.evaluate().isNotEmpty) {
        await tester.tap(askOmi);
        await _pumpFor(tester, 2000);
      }

      WidgetsBinding.instance.removeTimingsCallback(transCallback);
      final toChatMetrics = _calculateInteraction('Home->Chat', timings);
      allInteractions['home_to_chat'] = toChatMetrics;
      _printInteraction(toChatMetrics);

      // ── INTERACTION 3: Chat message send ──
      debugPrint('');
      debugPrint('[5/7] Profiling: Chat message send...');

      timings = <FrameTiming>[];
      void chatCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(chatCallback);

      final textField = find.byType(TextField);
      if (textField.evaluate().isNotEmpty) {
        await tester.enterText(textField.first, 'test message');
        await _pumpFor(tester, 500);

        final sendButton = find.byIcon(Icons.send);
        if (sendButton.evaluate().isNotEmpty) {
          await tester.tap(sendButton);
        } else {
          final altSend = find.byIcon(Icons.arrow_upward);
          if (altSend.evaluate().isNotEmpty) {
            await tester.tap(altSend);
          }
        }
        // Profile during AI response rendering
        for (int i = 0; i < 100; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }
      } else {
        await _pumpFor(tester, 10000);
      }

      WidgetsBinding.instance.removeTimingsCallback(chatCallback);
      final chatSendMetrics = _calculateInteraction('Chat Send', timings);
      allInteractions['chat_send'] = chatSendMetrics;
      _printInteraction(chatSendMetrics);

      // ── INTERACTION 4: Chat -> Home transition ──
      debugPrint('');
      debugPrint('[6/7] Profiling: Chat -> Home transition...');

      timings = <FrameTiming>[];
      void backCallback(List<FrameTiming> t) => timings.addAll(t);
      WidgetsBinding.instance.addTimingsCallback(backCallback);

      await tester.pageBack();
      await _pumpFor(tester, 2000);

      WidgetsBinding.instance.removeTimingsCallback(backCallback);
      final backMetrics = _calculateInteraction('Chat->Home', timings);
      allInteractions['chat_to_home'] = backMetrics;
      _printInteraction(backMetrics);

      // ── FINAL SUMMARY ──
      debugPrint('');
      debugPrint('[7/7] Summary');
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║              RESPONSIVENESS SUMMARY                         ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Interaction      │ Frames │ Avg ms │ P95 ms │ Janky %      ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      int totalFrames = 0;
      int totalJanky = 0;
      double totalBuildUs = 0;

      for (final entry in allInteractions.entries) {
        final m = entry.value;
        totalFrames += m.totalFrames;
        totalJanky += m.jankyFrames;
        debugPrint(
          '║ ${m.label.padRight(17)}│ ${m.totalFrames.toString().padLeft(6)} │ ${m.avgFrameMs.toStringAsFixed(2).padLeft(6)} │ ${m.p95FrameMs.toStringAsFixed(2).padLeft(6)} │ ${m.jankyPercent.toStringAsFixed(1).padLeft(5)}%       ║',
        );
      }

      final overallJankyPct = totalFrames > 0 ? (totalJanky / totalFrames * 100) : 0.0;
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint(
        '║ OVERALL          │ ${totalFrames.toString().padLeft(6)} │        │        │ ${overallJankyPct.toStringAsFixed(1).padLeft(5)}%       ║',
      );
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Pass/Fail evaluation
      debugPrint('');
      final avgFrameTimes = allInteractions.values.where((m) => m.totalFrames > 0).map((m) => m.avgFrameMs);
      final overallAvgFrame = avgFrameTimes.isNotEmpty
          ? avgFrameTimes.reduce((a, b) => a + b) / avgFrameTimes.length
          : 0.0;

      final passAvg = overallAvgFrame < 16.0;
      final passJanky = overallJankyPct < 5.0;

      debugPrint(
        'Avg frame time: ${overallAvgFrame.toStringAsFixed(2)} ms (threshold: < 16ms) ${passAvg ? "PASS" : "FAIL"}',
      );
      debugPrint(
        'Janky frames:   ${overallJankyPct.toStringAsFixed(1)}% (threshold: < 5%) ${passJanky ? "PASS" : "FAIL"}',
      );

      // Write results
      _writeResults(allInteractions, overallAvgFrame, overallJankyPct);

      // Assertions
      expect(
        overallJankyPct,
        lessThan(25.0),
        reason: 'Janky frames should be < 25% (actual: ${overallJankyPct.toStringAsFixed(1)}%)',
      );
    });
  });
}

class _InteractionMetrics {
  final String label;
  final int totalFrames;
  final double avgFrameMs;
  final double p95FrameMs;
  final double peakFrameMs;
  final int jankyFrames;
  final double jankyPercent;

  _InteractionMetrics({
    required this.label,
    required this.totalFrames,
    required this.avgFrameMs,
    required this.p95FrameMs,
    required this.peakFrameMs,
    required this.jankyFrames,
    required this.jankyPercent,
  });
}

_InteractionMetrics _calculateInteraction(String label, List<FrameTiming> timings) {
  if (timings.isEmpty) {
    return _InteractionMetrics(
      label: label,
      totalFrames: 0,
      avgFrameMs: 0,
      p95FrameMs: 0,
      peakFrameMs: 0,
      jankyFrames: 0,
      jankyPercent: 0,
    );
  }

  final frameTimes =
      timings.map((t) => (t.buildDuration.inMicroseconds + t.rasterDuration.inMicroseconds).toDouble()).toList()
        ..sort();

  final avgFrame = frameTimes.reduce((a, b) => a + b) / frameTimes.length;
  final p95Frame = frameTimes[(frameTimes.length * 0.95).toInt()];
  final peakFrame = frameTimes.last;

  final janky = frameTimes.where((t) => t > 16000).length; // > 16ms in microseconds

  return _InteractionMetrics(
    label: label,
    totalFrames: timings.length,
    avgFrameMs: avgFrame / 1000,
    p95FrameMs: p95Frame / 1000,
    peakFrameMs: peakFrame / 1000,
    jankyFrames: janky,
    jankyPercent: (janky / timings.length * 100),
  );
}

void _printInteraction(_InteractionMetrics m) {
  debugPrint('      ┌─────────────────────────────────────');
  debugPrint('      │ ${m.label}');
  debugPrint('      ├─────────────────────────────────────');
  debugPrint('      │ Frames:     ${m.totalFrames.toString().padLeft(6)}');
  debugPrint('      │ Avg frame:  ${m.avgFrameMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ P95 frame:  ${m.p95FrameMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Peak frame: ${m.peakFrameMs.toStringAsFixed(2).padLeft(6)} ms');
  debugPrint('      │ Janky:      ${m.jankyFrames.toString().padLeft(6)} (${m.jankyPercent.toStringAsFixed(1)}%)');
  debugPrint('      └─────────────────────────────────────');
}

void _writeResults(Map<String, _InteractionMetrics> results, double overallAvgFrame, double overallJankyPct) {
  try {
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('/tmp/omi_perf_responsiveness_$timestamp.json');
    final buffer = StringBuffer();
    buffer.writeln('{');
    buffer.writeln('  "test": "responsiveness",');
    buffer.writeln('  "overall_avg_frame_ms": ${overallAvgFrame.toStringAsFixed(3)},');
    buffer.writeln('  "overall_janky_percent": ${overallJankyPct.toStringAsFixed(2)},');
    buffer.writeln('  "interactions": {');
    final entries = results.entries.toList();
    for (int i = 0; i < entries.length; i++) {
      final m = entries[i].value;
      buffer.writeln('    "${entries[i].key}": {');
      buffer.writeln('      "label": "${m.label}",');
      buffer.writeln('      "total_frames": ${m.totalFrames},');
      buffer.writeln('      "avg_frame_ms": ${m.avgFrameMs.toStringAsFixed(3)},');
      buffer.writeln('      "p95_frame_ms": ${m.p95FrameMs.toStringAsFixed(3)},');
      buffer.writeln('      "peak_frame_ms": ${m.peakFrameMs.toStringAsFixed(3)},');
      buffer.writeln('      "janky_frames": ${m.jankyFrames},');
      buffer.writeln('      "janky_percent": ${m.jankyPercent.toStringAsFixed(2)}');
      buffer.writeln('    }${i < entries.length - 1 ? "," : ""}');
    }
    buffer.writeln('  }');
    buffer.writeln('}');
    file.writeAsStringSync(buffer.toString());
    debugPrint('Results saved to: ${file.path}');
  } catch (e) {
    debugPrint('Could not save results: $e');
  }
}

// ─── Shared helpers ──────────────────────────────────────────────────

Future<void> _pumpFor(WidgetTester tester, int milliseconds) async {
  final iterations = milliseconds ~/ 100;
  for (int i = 0; i < iterations; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _dismissAnyPopup(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 100));
  if (find.text('Loving Omi?').evaluate().isNotEmpty) {
    for (final text in ['Maybe later', 'Maybe Later']) {
      final btn = find.text(text);
      if (btn.evaluate().isNotEmpty) {
        await tester.tap(btn.first, warnIfMissed: false);
        await _pumpFor(tester, 500);
        return;
      }
    }
  }
  for (final text in ['Skip for now', 'Skip', 'Not now']) {
    final btn = find.text(text);
    if (btn.evaluate().isNotEmpty) {
      await tester.tap(btn.first, warnIfMissed: false);
      await _pumpFor(tester, 500);
      return;
    }
  }
}

Future<void> _handleOnboardingIfNeeded(WidgetTester tester) async {
  debugPrint('      Checking for onboarding...');
  if (find.text('Ask Omi').evaluate().isNotEmpty) {
    debugPrint('      Already on home screen');
    return;
  }

  final signIn = find.text('Sign in with Google');
  if (signIn.evaluate().isNotEmpty) {
    debugPrint('      Found auth screen');
    await tester.tap(signIn);
    await _pumpFor(tester, 2000);
    debugPrint('      >>> Please complete sign-in on device <<<');
    for (int i = 0; i < 120; i++) {
      await tester.pump(const Duration(milliseconds: 500));
      if (find.text('Ask Omi').evaluate().isNotEmpty) return;
      final cont = find.text('Continue');
      if (cont.evaluate().isNotEmpty) {
        await tester.tap(cont.first);
        await _pumpFor(tester, 2000);
      }
    }
  }

  for (int attempt = 0; attempt < 20; attempt++) {
    await _pumpFor(tester, 500);
    if (find.text('Ask Omi').evaluate().isNotEmpty) return;
    for (final text in ['Continue', 'Skip for now', 'Maybe Later']) {
      final btn = find.text(text);
      if (btn.evaluate().isNotEmpty) {
        await tester.tap(btn.first);
        await _pumpFor(tester, 2000);
        break;
      }
    }
  }
}
