import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

/// Standalone engine/driver smoke. No Omi bootstrap, auth, backend or native I/O.
/// Deliberately does not measure the production shell or seeded product scenarios.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('physical profile transport smoke', (tester) async {
    const runId = String.fromEnvironment('PERF_DEVICE_RUN_ID');
    expect(kProfileMode, isTrue, reason: 'Use flutter drive --profile on an approved physical device');
    expect(Platform.isIOS || Platform.isAndroid, isTrue);
    expect(runId, isNotEmpty);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ListView.builder(
          key: const ValueKey('device-smoke-list'),
          itemCount: 200,
          itemExtent: 64,
          itemBuilder: (_, index) => ListTile(title: Text('Fixture row $index')),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final timings = <FrameTiming>[];
    void record(List<FrameTiming> batch) => timings.addAll(batch);
    SchedulerBinding.instance.addTimingsCallback(record);
    try {
      for (var i = 0; i < 12; i++) {
        await tester.fling(find.byKey(const ValueKey('device-smoke-list')), Offset(0, i < 6 ? -350 : 350), 900);
        await tester.pumpAndSettle();
      }
      // Engine timings arrive in batches. Wait in real time for the last batch.
      await tester.runAsync(() => Future<void>.delayed(const Duration(seconds: 1)));
    } finally {
      SchedulerBinding.instance.removeTimingsCallback(record);
    }
    expect(timings.length, greaterThanOrEqualTo(10), reason: 'Missing real engine frame timings');
    expect(timings.any((frame) => frame.rasterDuration.inMicroseconds > 0), isTrue);
    binding.reportData = <String, dynamic>{
      'perf_device_smoke': <String, dynamic>{
        'schema': 'omi-perf-device-smoke/v1',
        'scope': 'standalone_shell_smoke',
        'run_id': runId,
        'build_mode': kProfileMode ? 'profile' : 'other',
        'platform': Platform.operatingSystem,
        'complete': true,
        'frame_count': timings.length,
        'build_us': timings.map((frame) => frame.buildDuration.inMicroseconds).toList(),
        'raster_us': timings.map((frame) => frame.rasterDuration.inMicroseconds).toList(),
        'total_us': timings.map((frame) => frame.totalSpan.inMicroseconds).toList(),
      },
    };
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
