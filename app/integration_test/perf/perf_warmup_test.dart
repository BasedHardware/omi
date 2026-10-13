/// Additive warm-up lens; run from app/:
/// PERF_SCORECARD_DIR=/tmp/omi-perf flutter test --no-pub -d flutter-tester
///   --dart-define=OMI_APP_PROFILE=local_dev integration_test/perf/perf_warmup_test.dart
///
/// Same PerfWorld seed, datasets, loopback HTTP, synthetic auth and platform
/// boundaries as the steady-state lane. This is a harness boot, not main():
/// native launch, Firebase, hardware and production network are not measured.
/// Milestones are cumulative monotonic wall-clock ms from before seed(), not
/// virtual pump durations. Backend readiness observes the imported boot's
/// published server at 1 ms intervals and verifies a real loopback response;
/// that probe overlaps seeding and adds a small observer cost.
/// Windows [0,5s) and [5s,15s) share that origin, including boot's frameless
/// time. Fixed 16 ms virtual pumps are paced with real 16 ms delays (not vsync).
/// FrameTiming uses vsyncStart timestamps, including delayed callback batches.
/// Host UI samples use post-frame completion time and exclude idle frames as
/// in the existing helper. They are reported separately, never as GPU timings.
/// Host scheduling/debug/JIT noise prevents device-latency or cold-launch claims.
/// Detail-to-chat includes 25 paced pumps before pop and 25 after pop for
/// route transitions; its cumulative milestone is not isolated chat init cost.
/// After the first navigations, a fixed triangle-wave chat scroll exercises
/// warm-up frames; sample counts depend on host throughput. No performance gate.
library;

import 'dart:convert';
import 'dart:developer';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';

import '../journeys/support/hermetic_boot.dart';
import 'perf_instrumentation.dart';
import 'perf_scenarios.dart';

class _WarmupInstrumentation extends PerfInstrumentation {
  _WarmupInstrumentation(this.clock);
  final Stopwatch clock;
  final samples = <({int elapsedUs, double ms})>[];

  @override
  void recordUiFrame(double ms, int callbacks) {
    if (active) samples.add((elapsedUs: clock.elapsedMicroseconds, ms: ms));
    super.recordUiFrame(ms, callbacks);
  }
}

Map<String, Object?> _frameStats(List<double> values) {
  const budget = 1000 / 60;
  final jank = values.where((ms) => ms > budget).length;
  return {
    'frame_count': values.length,
    'total_ms': values.isEmpty ? null : quantiles(values),
    'p90_ms': values.isEmpty ? null : quantile(values, .9),
    'jank_threshold_ms': budget,
    'jank_count': jank,
    'jank_percent': values.isEmpty ? null : 100 * jank / values.length,
  };
}

Future<void> _observeBackend(Stopwatch clock, Map<String, double> phases) async {
  final deadline = clock.elapsed + const Duration(seconds: 10);
  while (JourneyHermeticBoot.backend == null) {
    if (clock.elapsed >= deadline) throw StateError('Fixture backend did not become ready');
    await Future<void>.delayed(const Duration(milliseconds: 1));
  }
  final uri = Uri.parse(JourneyHermeticBoot.backend!.baseUrl).resolve('v1/conversations');
  if (uri.scheme != 'http' || uri.host != '127.0.0.1') throw StateError('Readiness probe must be loopback');
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
  try {
    final response = await (await client.getUrl(uri)).close().timeout(const Duration(seconds: 5));
    if (response.statusCode != HttpStatus.ok) throw StateError('Fixture readiness: ${response.statusCode}');
    await response.drain<void>();
    phases['fixture_backend_up_ms'] = clock.elapsedMicroseconds / 1000;
  } finally {
    client.close(force: true);
  }
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.onlyPumps;
  testWidgets('measure harness warm-up from seed through fifteen seconds', (tester) async {
    binding.testTextInput.register();
    final world = PerfWorld();
    final phases = <String, double>{};
    final clock = Stopwatch();
    final collector = _WarmupInstrumentation(clock);
    var seeded = false;
    addTearDown(() async {
      if (collector.active) collector.stop(binding);
      await tester.pumpWidget(const SizedBox.shrink());
      if (seeded) await tester.runAsync(world.close);
    });
    // Fresh process/test, never a cached backend from another scenario.
    expect(JourneyHermeticBoot.backend, isNull);
    final timelineOrigin = Timeline.now;
    clock.start();
    collector.start(binding);
    await tester.runAsync(() async {
      await Future.wait<void>([
        world.seed().then((_) {
          seeded = true;
          phases['providers_first_ready_ms'] = clock.elapsedMicroseconds / 1000;
        }),
        _observeBackend(clock, phases),
      ]);
    });
    expect(seeded, isTrue);
    await world.boot(tester);

    Future<void> pacedFrame() async {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 16)));
      await tester.pump(const Duration(milliseconds: 16));
    }

    Future<void> firstVisibleFrame(Finder finder, String phase) async {
      // No settle/pre-warm: record the first hit-testable page frame.
      await tester.pump();
      while (finder.hitTestable().evaluate().isEmpty) {
        if (clock.elapsed >= const Duration(seconds: 15)) fail('$phase not visible within warm-up');
        await pacedFrame();
      }
      phases[phase] = clock.elapsedMicroseconds / 1000;
    }

    globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(
      builder: (_) => ConversationsPage(
        requestInitialLoad: false,
        loadRecaps: () async => (items: <DailySummary>[], ok: true),
      ),
    ));
    await firstVisibleFrame(find.byKey(const ValueKey('perf-conv-0')), 'first_home_frame_ms');
    await tester.tap(find.byKey(const ValueKey('perf-conv-0')));
    await firstVisibleFrame(find.byType(ConversationDetailPage), 'first_detail_open_ms');
    expect(find.text('Performance conversation 0'), findsWidgets);
    // Finish the route transition before popping, without an unmeasured warm-up.
    for (var i = 0; i < 25; i++) {
      await pacedFrame();
    }
    globalNavigatorKey.currentState!.pop();
    for (var i = 0; i < 25; i++) {
      await pacedFrame();
    }
    globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => const ChatPage()));
    await firstVisibleFrame(find.byType(ChatPage), 'first_chat_open_ms');
    expect(find.byKey(const ValueKey('omi.chat.input')), findsOneWidget);

    var frame = 0;
    while (clock.elapsed < const Duration(seconds: 15)) {
      final scrollables = find.descendant(of: find.byType(ChatPage), matching: find.byType(Scrollable));
      for (final element in scrollables.evaluate()) {
        final state = (element as StatefulElement).state as ScrollableState;
        final position = state.position;
        if (position.axis == Axis.vertical && position.hasContentDimensions && position.maxScrollExtent > 0) {
          final step = frame % 120;
          final fraction = (step <= 60 ? step : 120 - step) / 60;
          position.jumpTo(position.minScrollExtent + fraction * (position.maxScrollExtent - position.minScrollExtent));
        }
      }
      frame++;
      await pacedFrame();
    }
    collector.endWindow();
    // Flush batched engine callbacks without extending the observation window.
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 250)));
    collector.stop(binding);

    Map<String, Object?> window(int startUs, int endUs) {
      final timings = collector.timings.where((timing) {
        final elapsed = timing.timestampInMicroseconds(FramePhase.vsyncStart) - timelineOrigin;
        return elapsed >= startUs && elapsed < endUs;
      }).toList();
      final ui =
          collector.samples.where((s) => s.elapsedUs >= startUs && s.elapsedUs < endUs).map((s) => s.ms).toList();
      expect(ui, isNotEmpty, reason: 'Warm-up window must exercise real active UI frames');
      final total = timings.map((t) => (t.buildDuration + t.rasterDuration).inMicroseconds / 1000).toList();
      return {
        'start_ms': startUs / 1000,
        'end_ms': endUs / 1000,
        'measurement': total.isEmpty ? 'frame_timing_unavailable' : 'engine_frame_timing',
        ..._frameStats(total),
        'build_ms':
            timings.isEmpty ? null : quantiles(timings.map((t) => t.buildDuration.inMicroseconds / 1000).toList()),
        'raster_ms':
            timings.isEmpty ? null : quantiles(timings.map((t) => t.rasterDuration.inMicroseconds / 1000).toList()),
        'host_ui_pipeline': {'measurement': 'host_ui_pipeline_wall_clock', ..._frameStats(ui)},
      };
    }

    final scorecard = <String, Object?>{
      'schema': 'omi-mobile-warmup/v1',
      'lane': 'host_flutter_tester',
      'dataset_sizes': datasetSizes,
      'phase_origin': 'before_PerfWorld_seed',
      'phase_semantics': 'cumulative_wall_clock_ms',
      'phases': phases,
      'frames_0_5s': window(0, 5000000),
      'frames_5_15s': window(5000000, 15000000),
      'workload': 'home row tap to detail; return; open chat; 120-pump triangle-wave chat scroll',
      'complete': phases.length == 5,
    };
    expect(phases.values.every((ms) => ms >= 0 && ms < 15000), isTrue);
    expect(phases['fixture_backend_up_ms'], lessThanOrEqualTo(phases['providers_first_ready_ms']!));
    final directory = Directory(Platform.environment['PERF_SCORECARD_DIR'] ?? '/tmp/omi-perf')
      ..createSync(recursive: true);
    final file = File('${directory.path}/warmup-${DateTime.now().toUtc().microsecondsSinceEpoch}.json');
    file.writeAsStringSync(const JsonEncoder.withIndent('  ').convert(scorecard));
    binding.reportData = {...?binding.reportData, 'perf_warmup': scorecard};
    debugPrint('PERF_WARMUP=${file.path}');
  });
}
