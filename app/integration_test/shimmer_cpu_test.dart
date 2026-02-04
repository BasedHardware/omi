import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shimmer/shimmer.dart';

/// Shimmer CPU Usage Test
///
/// This test confirms that the Shimmer widget causes continuous CPU usage
/// even when idle, compared to a static widget.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/shimmer_cpu_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Shimmer CPU Usage Test', () {
    testWidgets('Compare frame counts: Shimmer vs Static widget', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         SHIMMER CPU USAGE TEST                               ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // === TEST 1: Static widget (baseline) ===
      debugPrint('[1/3] Testing STATIC widget (10 seconds)...');
      debugPrint('      Expected: Minimal frames (only initial render)');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            backgroundColor: Colors.black,
            body: Center(
              child: Container(
                width: 300,
                height: 100,
                decoration: BoxDecoration(
                  color: const Color(0xFF2A2A32),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Center(
                  child: Text(
                    'Processing...',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final staticTimings = <FrameTiming>[];
      void staticCallback(List<FrameTiming> timings) {
        staticTimings.addAll(timings);
      }

      WidgetsBinding.instance.addTimingsCallback(staticCallback);

      // Pump for 10 seconds without any interaction
      for (int i = 0; i < 100; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(staticCallback);

      debugPrint('      Static widget frames: ${staticTimings.length}');

      // === TEST 2: Shimmer widget ===
      debugPrint('');
      debugPrint('[2/3] Testing SHIMMER widget (10 seconds)...');
      debugPrint('      Expected: Many frames (continuous animation)');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            backgroundColor: Colors.black,
            body: Center(
              child: Shimmer.fromColors(
                baseColor: const Color(0xFF2A2A32),
                highlightColor: const Color(0xFF3D3D47),
                child: Container(
                  width: 300,
                  height: 100,
                  decoration: BoxDecoration(
                    color: const Color(0xFF2A2A32),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Center(
                    child: Text(
                      'Processing...',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      // DON'T use pumpAndSettle - Shimmer never settles!
      await tester.pump();

      final shimmerTimings = <FrameTiming>[];
      void shimmerCallback(List<FrameTiming> timings) {
        shimmerTimings.addAll(timings);
      }

      WidgetsBinding.instance.addTimingsCallback(shimmerCallback);

      // Pump for 10 seconds
      for (int i = 0; i < 100; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(shimmerCallback);

      debugPrint('      Shimmer widget frames: ${shimmerTimings.length}');

      // === TEST 3: Shimmer with RepaintBoundary ===
      debugPrint('');
      debugPrint('[3/3] Testing SHIMMER + RepaintBoundary (10 seconds)...');
      debugPrint('      Testing if RepaintBoundary reduces CPU impact');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            backgroundColor: Colors.black,
            body: Center(
              child: RepaintBoundary(
                child: Shimmer.fromColors(
                  baseColor: const Color(0xFF2A2A32),
                  highlightColor: const Color(0xFF3D3D47),
                  child: Container(
                    width: 300,
                    height: 100,
                    decoration: BoxDecoration(
                      color: const Color(0xFF2A2A32),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Center(
                      child: Text(
                        'Processing...',
                        style: TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      // DON'T use pumpAndSettle - Shimmer never settles!
      await tester.pump();

      final boundaryTimings = <FrameTiming>[];
      void boundaryCallback(List<FrameTiming> timings) {
        boundaryTimings.addAll(timings);
      }

      WidgetsBinding.instance.addTimingsCallback(boundaryCallback);

      // Pump for 10 seconds
      for (int i = 0; i < 100; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(boundaryCallback);

      debugPrint('      Shimmer+Boundary frames: ${boundaryTimings.length}');

      // === RESULTS ===
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    TEST RESULTS                              ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Widget Type              │ Frames (10s) │ Frames/sec         ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint(
          '║ Static (baseline)        │ ${staticTimings.length.toString().padLeft(12)} │ ${(staticTimings.length / 10).toStringAsFixed(1).padLeft(10)}/s       ║');
      debugPrint(
          '║ Shimmer                  │ ${shimmerTimings.length.toString().padLeft(12)} │ ${(shimmerTimings.length / 10).toStringAsFixed(1).padLeft(10)}/s       ║');
      debugPrint(
          '║ Shimmer+RepaintBoundary  │ ${boundaryTimings.length.toString().padLeft(12)} │ ${(boundaryTimings.length / 10).toStringAsFixed(1).padLeft(10)}/s       ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Calculate overhead
      final shimmerOverhead = shimmerTimings.length - staticTimings.length;
      final boundaryOverhead = boundaryTimings.length - staticTimings.length;

      debugPrint('');
      debugPrint('Analysis:');
      debugPrint('  Shimmer overhead: +$shimmerOverhead frames (+${(shimmerOverhead / 10).toStringAsFixed(1)}/s)');
      debugPrint(
          '  RepaintBoundary effect: ${boundaryOverhead < shimmerOverhead ? "Reduced by ${shimmerOverhead - boundaryOverhead} frames" : "No significant reduction"}');

      // Verify shimmer causes more frames
      if (shimmerTimings.length > staticTimings.length * 2) {
        debugPrint('');
        debugPrint('╔══════════════════════════════════════════════════════════════╗');
        debugPrint('║  ⚠️  CONFIRMED: Shimmer causes continuous frame rendering    ║');
        debugPrint('╚══════════════════════════════════════════════════════════════╝');
      }

      // Assertions
      expect(
        shimmerTimings.length,
        greaterThan(staticTimings.length),
        reason: 'Shimmer should cause more frames than static widget',
      );
    });

    testWidgets('Measure build time impact of Shimmer', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         SHIMMER BUILD TIME TEST                              ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Test ProcessingConversationWidget-like structure
      debugPrint('[1/2] Testing ProcessingConversationWidget structure...');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            backgroundColor: Colors.black,
            body: ListView(
              children: [
                // Simulate multiple processing conversations
                for (int i = 0; i < 3; i++)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: RepaintBoundary(
                      child: Shimmer.fromColors(
                        baseColor: const Color(0xFF2A2A32),
                        highlightColor: const Color(0xFF3D3D47),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 24,
                                  height: 24,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF2A2A32),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Container(
                                  width: 80,
                                  height: 24,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF35343B),
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                ),
                                const Spacer(),
                                Container(
                                  width: 50,
                                  height: 14,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF2A2A32),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Container(
                              width: double.maxFinite,
                              height: 16,
                              decoration: BoxDecoration(
                                color: const Color(0xFF2A2A32),
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      );
      // DON'T use pumpAndSettle - Shimmer never settles!
      await tester.pump();

      final multiShimmerTimings = <FrameTiming>[];
      void multiCallback(List<FrameTiming> timings) {
        multiShimmerTimings.addAll(timings);
      }

      WidgetsBinding.instance.addTimingsCallback(multiCallback);

      for (int i = 0; i < 100; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(multiCallback);

      debugPrint('      3x Shimmer widgets: ${multiShimmerTimings.length} frames');

      if (multiShimmerTimings.isNotEmpty) {
        final buildTimes = multiShimmerTimings.map((t) => t.buildDuration.inMicroseconds).toList()..sort();
        final avgBuild = buildTimes.reduce((a, b) => a + b) / buildTimes.length;
        final maxBuild = buildTimes.last;

        debugPrint('      Avg build time: ${(avgBuild / 1000).toStringAsFixed(2)} ms');
        debugPrint('      Max build time: ${(maxBuild / 1000).toStringAsFixed(2)} ms');
      }

      // === Alternative: Static skeleton ===
      debugPrint('');
      debugPrint('[2/2] Testing static skeleton alternative...');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            backgroundColor: Colors.black,
            body: ListView(
              children: [
                for (int i = 0; i < 3; i++)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 24,
                              height: 24,
                              decoration: BoxDecoration(
                                color: const Color(0xFF2A2A32),
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              decoration: BoxDecoration(
                                color: const Color(0xFF35343B),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: const Text(
                                'Processing...',
                                style: TextStyle(color: Colors.white70, fontSize: 14),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Container(
                          width: double.maxFinite,
                          height: 16,
                          decoration: BoxDecoration(
                            color: const Color(0xFF2A2A32),
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final staticSkeletonTimings = <FrameTiming>[];
      void staticSkeletonCallback(List<FrameTiming> timings) {
        staticSkeletonTimings.addAll(timings);
      }

      WidgetsBinding.instance.addTimingsCallback(staticSkeletonCallback);

      for (int i = 0; i < 100; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      WidgetsBinding.instance.removeTimingsCallback(staticSkeletonCallback);

      debugPrint('      Static skeleton: ${staticSkeletonTimings.length} frames');

      // === SUMMARY ===
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    RECOMMENDATION                            ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      final savings = multiShimmerTimings.length - staticSkeletonTimings.length;
      debugPrint('║ Replacing Shimmer with static skeleton would save:           ║');
      debugPrint('║   ~$savings frames over 10 seconds'.padRight(61) + '║');
      debugPrint('║   ~${(savings / 10).toStringAsFixed(0)} frames/second'.padRight(61) + '║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      expect(
        multiShimmerTimings.length,
        greaterThan(staticSkeletonTimings.length),
        reason: 'Shimmer skeleton should use more frames than static skeleton',
      );
    });
  });
}
