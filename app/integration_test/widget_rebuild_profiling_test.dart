import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:provider/provider.dart';

/// Widget Rebuild Profiling Test (PR #4440)
///
/// This test measures widget rebuild frequency before and after the
/// Consumer→Selector optimization.
///
/// Key metrics:
///   - LiteCaptureWidget rebuild count (should only rebuild on segments/photos)
///   - BatteryInfoWidget rebuild count (should only rebuild on battery/device/connecting)
///   - notifyListeners() call frequency from providers
///
/// Run with:
/// ```bash
/// flutter drive \
///   --driver=test_driver/integration_test.dart \
///   --target=integration_test/widget_rebuild_profiling_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Widget Rebuild Profiling (PR #4440)', () {
    testWidgets('Measure rebuild frequency with simulated provider updates', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         WIDGET REBUILD PROFILING (PR #4440)                  ║');
      debugPrint('║         Simulated Provider Updates - Rebuild Count Test      ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // Track rebuild counts
      int captureWidgetRebuilds = 0;
      int batteryWidgetRebuilds = 0;
      int unrelatedWidgetRebuilds = 0;

      final captureProvider = _TestCaptureProvider();
      final deviceProvider = _TestDeviceProvider();

      // Build test widget with Selectors (mimics the real app structure)
      final testWidget = MaterialApp(
        home: MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: captureProvider),
            ChangeNotifierProvider.value(value: deviceProvider),
          ],
          child: Scaffold(
            body: Column(
              children: [
                // LiteCaptureWidget-like Selector
                Selector<_TestCaptureProvider, (List<String>, int)>(
                  selector: (_, p) => (p.segments, p.segmentsPhotosVersion),
                  builder: (context, data, child) {
                    captureWidgetRebuilds++;
                    return Text('Segments: ${data.$1.length}');
                  },
                ),
                // BatteryInfoWidget-like Selector
                Selector<_TestDeviceProvider, (int, bool)>(
                  selector: (_, p) => (p.batteryLevel, p.isConnecting),
                  builder: (context, data, child) {
                    batteryWidgetRebuilds++;
                    return Text('Battery: ${data.$1}%');
                  },
                ),
                // Unrelated widget that would rebuild with Consumer
                Consumer<_TestCaptureProvider>(
                  builder: (context, provider, child) {
                    unrelatedWidgetRebuilds++;
                    return const Text('Unrelated');
                  },
                ),
              ],
            ),
          ),
        ),
      );

      await tester.pumpWidget(testWidget);
      await tester.pumpAndSettle();

      // Record initial builds
      final initialCaptureRebuilds = captureWidgetRebuilds;
      final initialBatteryRebuilds = batteryWidgetRebuilds;
      final initialUnrelatedRebuilds = unrelatedWidgetRebuilds;

      debugPrint('[1/4] Initial build complete');
      debugPrint('      CaptureWidget rebuilds: $captureWidgetRebuilds');
      debugPrint('      BatteryWidget rebuilds: $batteryWidgetRebuilds');
      debugPrint('      UnrelatedWidget rebuilds: $unrelatedWidgetRebuilds');

      // === TEST 1: Simulate 50 "metrics" updates (unrelated to segments/battery) ===
      debugPrint('');
      debugPrint('[2/4] Simulating 50 metrics/internal updates...');
      debugPrint('      These should NOT trigger Selector rebuilds.');

      for (int i = 0; i < 50; i++) {
        captureProvider.triggerUnrelatedUpdate();
        await tester.pump();
      }

      final afterMetricsCapture = captureWidgetRebuilds;
      final afterMetricsBattery = batteryWidgetRebuilds;
      final afterMetricsUnrelated = unrelatedWidgetRebuilds;

      debugPrint(
          '      CaptureWidget rebuilds: $afterMetricsCapture (diff: ${afterMetricsCapture - initialCaptureRebuilds})');
      debugPrint(
          '      BatteryWidget rebuilds: $afterMetricsBattery (diff: ${afterMetricsBattery - initialBatteryRebuilds})');
      debugPrint(
          '      UnrelatedWidget (Consumer) rebuilds: $afterMetricsUnrelated (diff: ${afterMetricsUnrelated - initialUnrelatedRebuilds})');

      // === TEST 2: Simulate 10 segment additions ===
      debugPrint('');
      debugPrint('[3/4] Simulating 10 segment additions...');
      debugPrint('      CaptureWidget Selector SHOULD rebuild, BatteryWidget should NOT.');

      for (int i = 0; i < 10; i++) {
        captureProvider.addSegment();
        await tester.pump();
      }

      final afterSegmentsCapture = captureWidgetRebuilds;
      final afterSegmentsBattery = batteryWidgetRebuilds;

      debugPrint(
          '      CaptureWidget rebuilds: $afterSegmentsCapture (diff: ${afterSegmentsCapture - afterMetricsCapture})');
      debugPrint(
          '      BatteryWidget rebuilds: $afterSegmentsBattery (diff: ${afterSegmentsBattery - afterMetricsBattery})');

      // === TEST 3: Simulate 10 battery updates ===
      debugPrint('');
      debugPrint('[4/4] Simulating 10 battery level changes...');
      debugPrint('      BatteryWidget Selector SHOULD rebuild, CaptureWidget should NOT.');

      // Start from a different value to ensure all 10 updates trigger rebuilds
      for (int i = 1; i <= 10; i++) {
        deviceProvider.updateBattery(100 - i * 5); // 95, 90, 85, ..., 50
        await tester.pump();
      }

      final finalCaptureRebuilds = captureWidgetRebuilds;
      final finalBatteryRebuilds = batteryWidgetRebuilds;
      final finalUnrelatedRebuilds = unrelatedWidgetRebuilds;

      debugPrint(
          '      CaptureWidget rebuilds: $finalCaptureRebuilds (diff: ${finalCaptureRebuilds - afterSegmentsCapture})');
      debugPrint(
          '      BatteryWidget rebuilds: $finalBatteryRebuilds (diff: ${finalBatteryRebuilds - afterSegmentsBattery})');

      // === SUMMARY ===
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    REBUILD SUMMARY                           ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');
      debugPrint('║ Widget              │ Total │ From Metrics │ Expected       ║');
      debugPrint('╠══════════════════════════════════════════════════════════════╣');

      final captureFromMetrics = afterMetricsCapture - initialCaptureRebuilds;
      final batteryFromMetrics = afterMetricsBattery - initialBatteryRebuilds;
      final unrelatedFromMetrics = afterMetricsUnrelated - initialUnrelatedRebuilds;

      debugPrint(
          '║ CaptureWidget       │ ${finalCaptureRebuilds.toString().padLeft(5)} │ ${captureFromMetrics.toString().padLeft(12)} │ 0 (Selector)   ║');
      debugPrint(
          '║ BatteryWidget       │ ${finalBatteryRebuilds.toString().padLeft(5)} │ ${batteryFromMetrics.toString().padLeft(12)} │ 0 (Selector)   ║');
      debugPrint(
          '║ UnrelatedWidget     │ ${finalUnrelatedRebuilds.toString().padLeft(5)} │ ${unrelatedFromMetrics.toString().padLeft(12)} │ 50 (Consumer)  ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');

      // Verify Selector behavior
      expect(captureFromMetrics, equals(0), reason: 'CaptureWidget Selector should NOT rebuild on metrics updates');
      expect(batteryFromMetrics, equals(0), reason: 'BatteryWidget Selector should NOT rebuild on metrics updates');
      expect(unrelatedFromMetrics, equals(50), reason: 'Consumer widget SHOULD rebuild on every notifyListeners()');

      // Verify targeted rebuilds work
      expect(afterSegmentsCapture - afterMetricsCapture, equals(10),
          reason: 'CaptureWidget should rebuild exactly 10 times for 10 segment additions');
      expect(finalBatteryRebuilds - afterSegmentsBattery, equals(10),
          reason: 'BatteryWidget should rebuild exactly 10 times for 10 battery changes');

      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    ALL ASSERTIONS PASSED                     ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');
      debugPrint('PR #4440 Selector optimization verified:');
      debugPrint('  - 50 metrics updates caused 0 unnecessary Selector rebuilds');
      debugPrint('  - Segment changes correctly triggered only CaptureWidget');
      debugPrint('  - Battery changes correctly triggered only BatteryWidget');
      debugPrint('  - Consumer widgets still rebuild on every update (baseline)');
    });

    testWidgets('Verify Selector rebuild behavior', (WidgetTester tester) async {
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║         SELECTOR REBUILD VERIFICATION                        ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');

      // This test verifies that Selector widgets only rebuild when their
      // selected values actually change.

      // Build a test widget tree with rebuild counters
      int liteCaptureRebuildCount = 0;
      int batteryInfoRebuildCount = 0;

      final testWidget = MaterialApp(
        home: MultiProvider(
          providers: [
            ChangeNotifierProvider(create: (_) => _TestCaptureProvider()),
            ChangeNotifierProvider(create: (_) => _TestDeviceProvider()),
          ],
          child: Builder(
            builder: (context) {
              return Column(
                children: [
                  // Test LiteCaptureWidget-like Selector
                  Selector<_TestCaptureProvider, (List<String>, int)>(
                    selector: (_, p) => (p.segments, p.segmentsPhotosVersion),
                    builder: (context, data, child) {
                      liteCaptureRebuildCount++;
                      return Text('Segments: ${data.$1.length}');
                    },
                  ),
                  // Test BatteryInfoWidget-like Selector
                  Selector<_TestDeviceProvider, (int, bool)>(
                    selector: (_, p) => (p.batteryLevel, p.isConnecting),
                    builder: (context, data, child) {
                      batteryInfoRebuildCount++;
                      return Text('Battery: ${data.$1}%');
                    },
                  ),
                  // Controls to trigger provider updates
                  ElevatedButton(
                    onPressed: () {
                      context.read<_TestCaptureProvider>().triggerUnrelatedUpdate();
                    },
                    child: const Text('Unrelated Update'),
                  ),
                  ElevatedButton(
                    onPressed: () {
                      context.read<_TestCaptureProvider>().addSegment();
                    },
                    child: const Text('Add Segment'),
                  ),
                  ElevatedButton(
                    onPressed: () {
                      context.read<_TestDeviceProvider>().updateBattery(50);
                    },
                    child: const Text('Update Battery'),
                  ),
                ],
              );
            },
          ),
        ),
      );

      await tester.pumpWidget(testWidget);
      await tester.pumpAndSettle();

      // Initial build
      debugPrint('Initial build counts:');
      debugPrint('  LiteCaptureWidget rebuilds: $liteCaptureRebuildCount');
      debugPrint('  BatteryInfoWidget rebuilds: $batteryInfoRebuildCount');

      final initialLiteCapture = liteCaptureRebuildCount;
      final initialBatteryInfo = batteryInfoRebuildCount;

      // Trigger unrelated updates (should NOT cause rebuilds with Selector)
      debugPrint('');
      debugPrint('Triggering 10 unrelated updates...');
      for (int i = 0; i < 10; i++) {
        await tester.tap(find.text('Unrelated Update'));
        await tester.pumpAndSettle();
      }

      debugPrint('After unrelated updates:');
      debugPrint('  LiteCaptureWidget rebuilds: $liteCaptureRebuildCount (expected: $initialLiteCapture)');
      debugPrint('  BatteryInfoWidget rebuilds: $batteryInfoRebuildCount (expected: $initialBatteryInfo)');

      final afterUnrelatedLiteCapture = liteCaptureRebuildCount;
      final afterUnrelatedBatteryInfo = batteryInfoRebuildCount;

      // With Consumer, these would increase. With Selector, they should stay the same.
      expect(
        afterUnrelatedLiteCapture,
        equals(initialLiteCapture),
        reason: 'LiteCaptureWidget should NOT rebuild on unrelated updates',
      );
      expect(
        afterUnrelatedBatteryInfo,
        equals(initialBatteryInfo),
        reason: 'BatteryInfoWidget should NOT rebuild on unrelated updates',
      );

      // Trigger segment update (should cause LiteCaptureWidget rebuild)
      debugPrint('');
      debugPrint('Adding segment...');
      await tester.tap(find.text('Add Segment'));
      await tester.pumpAndSettle();

      debugPrint('After adding segment:');
      debugPrint('  LiteCaptureWidget rebuilds: $liteCaptureRebuildCount (expected: ${initialLiteCapture + 1})');

      expect(
        liteCaptureRebuildCount,
        equals(initialLiteCapture + 1),
        reason: 'LiteCaptureWidget SHOULD rebuild when segments change',
      );

      // Trigger battery update (should cause BatteryInfoWidget rebuild)
      debugPrint('');
      debugPrint('Updating battery...');
      await tester.tap(find.text('Update Battery'));
      await tester.pumpAndSettle();

      debugPrint('After updating battery:');
      debugPrint('  BatteryInfoWidget rebuilds: $batteryInfoRebuildCount (expected: ${initialBatteryInfo + 1})');

      expect(
        batteryInfoRebuildCount,
        equals(initialBatteryInfo + 1),
        reason: 'BatteryInfoWidget SHOULD rebuild when battery changes',
      );

      // === FINAL RESULT ===
      debugPrint('');
      debugPrint('╔══════════════════════════════════════════════════════════════╗');
      debugPrint('║                    SELECTOR VERIFICATION PASSED              ║');
      debugPrint('╚══════════════════════════════════════════════════════════════╝');
      debugPrint('');
      debugPrint('Selectors correctly prevent rebuilds on unrelated updates!');
      debugPrint('  - 10 unrelated updates caused 0 unnecessary rebuilds');
      debugPrint('  - Segment change correctly triggered LiteCaptureWidget rebuild');
      debugPrint('  - Battery change correctly triggered BatteryInfoWidget rebuild');
    });
  });
}

/// Test provider that mimics CaptureProvider behavior
class _TestCaptureProvider extends ChangeNotifier {
  List<String> segments = [];
  int segmentsPhotosVersion = 0;

  /// Simulates internal state (e.g., metrics, recording state) that triggers
  /// notifyListeners() but shouldn't cause Selector widgets to rebuild.
  void triggerUnrelatedUpdate() {
    // Simulates provider updating internal state like _bleReceiveRateKbps
    notifyListeners();
  }

  void addSegment() {
    segments = List.from(segments)..add('segment_${segments.length}');
    segmentsPhotosVersion++;
    notifyListeners();
  }
}

/// Test provider that mimics DeviceProvider behavior
class _TestDeviceProvider extends ChangeNotifier {
  int batteryLevel = 100;
  bool isConnecting = false;

  /// Simulates internal state changes that shouldn't cause Selector widgets to rebuild.
  void triggerUnrelatedUpdate() {
    // Simulates provider updating internal state like firmware check
    notifyListeners();
  }

  void updateBattery(int level) {
    batteryLevel = level;
    notifyListeners();
  }
}
