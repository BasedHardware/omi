import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

/// Animation Performance Profiling Test
///
/// This test profiles the animation performance across different screens
/// to measure battery impact and frame rendering metrics.
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/animation_performance_test.dart \
///   --profile \
///   --flavor dev
/// ```
///
/// Or for more detailed profiling:
/// ```bash
/// flutter test integration_test/animation_performance_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Animation Performance Profiling', () {
    testWidgets('Profile home screen animations', (WidgetTester tester) async {
      // Import and run the app
      // Note: This requires the app to be in a logged-in state
      // For CI/CD, you'd want a test-specific entry point
      await tester.pumpWidget(const _TestApp());

      // Wait for app to fully initialize (use pump, NOT pumpAndSettle - animations never stop)
      for (int i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      // Check if we're on a screen (home or login)
      debugPrint('=== Starting Animation Performance Test ===');

      // Profile home screen for 10 seconds
      // This captures WaveformSection and ProcessingCapture animations
      debugPrint('Profiling HOME screen...');
      await binding.traceAction(
        () async {
          // Let animations run for 10 seconds
          for (int i = 0; i < 100; i++) {
            await tester.pump(const Duration(milliseconds: 100));
          }
        },
        reportKey: 'home_screen_animations',
      );
      debugPrint('[HOME] Timeline captured');

      debugPrint('=== Test Complete ===');
    });

    testWidgets('Profile with frame callback metrics', (WidgetTester tester) async {
      await tester.pumpWidget(const _TestApp());
      // Wait for app to initialize (use pump, NOT pumpAndSettle - animations never stop)
      for (int i = 0; i < 20; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      // Collect frame timing data manually
      final frameTimings = <FrameTiming>[];
      final frameCallback = (List<FrameTiming> timings) {
        frameTimings.addAll(timings);
      };

      // Register frame callback
      WidgetsBinding.instance.addTimingsCallback(frameCallback);

      debugPrint('=== Collecting Frame Metrics (30 seconds) ===');

      // Run for 30 seconds collecting frame data
      final stopwatch = Stopwatch()..start();
      while (stopwatch.elapsed < const Duration(seconds: 30)) {
        await tester.pump(const Duration(milliseconds: 16)); // ~60fps
      }

      // Remove callback
      WidgetsBinding.instance.removeTimingsCallback(frameCallback);

      // Analyze results
      if (frameTimings.isNotEmpty) {
        final buildTimes = frameTimings.map((t) => t.buildDuration.inMicroseconds).toList();
        final rasterTimes = frameTimings.map((t) => t.rasterDuration.inMicroseconds).toList();

        buildTimes.sort();
        rasterTimes.sort();

        final avgBuild = buildTimes.reduce((a, b) => a + b) / buildTimes.length;
        final avgRaster = rasterTimes.reduce((a, b) => a + b) / rasterTimes.length;
        final p50Build = buildTimes[buildTimes.length ~/ 2];
        final p90Build = buildTimes[(buildTimes.length * 0.9).toInt()];
        final p99Build = buildTimes[(buildTimes.length * 0.99).toInt()];

        debugPrint('');
        debugPrint('╔══════════════════════════════════════════════════════════════╗');
        debugPrint('║               FRAME METRICS SUMMARY                          ║');
        debugPrint('╠══════════════════════════════════════════════════════════════╣');
        debugPrint(
            '║ Total Frames: ${frameTimings.length.toString().padLeft(6)}                                     ║');
        debugPrint(
            '║ Build Time (avg): ${(avgBuild / 1000).toStringAsFixed(2).padLeft(8)} ms                         ║');
        debugPrint(
            '║ Build Time (p50): ${(p50Build / 1000).toStringAsFixed(2).padLeft(8)} ms                         ║');
        debugPrint(
            '║ Build Time (p90): ${(p90Build / 1000).toStringAsFixed(2).padLeft(8)} ms                         ║');
        debugPrint(
            '║ Build Time (p99): ${(p99Build / 1000).toStringAsFixed(2).padLeft(8)} ms                         ║');
        debugPrint(
            '║ Raster Time (avg): ${(avgRaster / 1000).toStringAsFixed(2).padLeft(7)} ms                         ║');
        debugPrint('╚══════════════════════════════════════════════════════════════╝');

        // Janky frame detection (>16ms = missed 60fps target)
        final jankyFrames = frameTimings
            .where((t) => t.buildDuration.inMilliseconds > 16 || t.rasterDuration.inMilliseconds > 16)
            .length;
        final jankyPercent = (jankyFrames / frameTimings.length * 100).toStringAsFixed(1);
        debugPrint('Janky Frames: $jankyFrames ($jankyPercent%)');
      } else {
        debugPrint('No frame timings collected');
      }
    });
  });
}

/// Minimal test app wrapper
/// In a real test, you'd import your actual app
class _TestApp extends StatelessWidget {
  const _TestApp();

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('Animation Performance Test'),
              const SizedBox(height: 20),
              // Simulate animations similar to the app
              const _AnimatedWidget(),
              const SizedBox(height: 20),
              const _ShimmerWidget(),
              const SizedBox(height: 20),
              const _TypingIndicatorWidget(),
            ],
          ),
        ),
      ),
    );
  }
}

/// Simulates WaveformSection-like animation
class _AnimatedWidget extends StatefulWidget {
  const _AnimatedWidget();

  @override
  State<_AnimatedWidget> createState() => _AnimatedWidgetState();
}

class _AnimatedWidgetState extends State<_AnimatedWidget> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 250), // Matches PR optimization
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Container(
          width: 200,
          height: 50,
          decoration: BoxDecoration(
            color: Colors.blue.withOpacity(0.3 + _controller.value * 0.7),
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Center(child: Text('Waveform Animation')),
        );
      },
    );
  }
}

/// Simulates Shimmer animation
class _ShimmerWidget extends StatefulWidget {
  const _ShimmerWidget();

  @override
  State<_ShimmerWidget> createState() => _ShimmerWidgetState();
}

class _ShimmerWidgetState extends State<_ShimmerWidget> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Container(
          width: 200,
          height: 30,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment(-1.0 + _controller.value * 2, 0),
              end: Alignment(_controller.value * 2, 0),
              colors: const [
                Colors.grey,
                Colors.white,
                Colors.grey,
              ],
            ),
            borderRadius: BorderRadius.circular(4),
          ),
        );
      },
    );
  }
}

/// Simulates TypingIndicator animation
class _TypingIndicatorWidget extends StatefulWidget {
  const _TypingIndicatorWidget();

  @override
  State<_TypingIndicatorWidget> createState() => _TypingIndicatorWidgetState();
}

class _TypingIndicatorWidgetState extends State<_TypingIndicatorWidget> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildDot(0.0),
        const SizedBox(width: 5),
        _buildDot(0.2),
        const SizedBox(width: 5),
        _buildDot(0.4),
      ],
    );
  }

  Widget _buildDot(double delay) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final value = (_controller.value + delay) % 1.0;
        return Transform.translate(
          offset: Offset(0, -5 * (value > 0.5 ? 1 - value : value)),
          child: Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: Colors.grey.withOpacity(0.5 + value * 0.5),
              shape: BoxShape.circle,
            ),
          ),
        );
      },
    );
  }
}
