import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'perf_instrumentation.dart';
import 'perf_scenarios.dart';
import 'perf_scorecard.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.onlyPumps;
  indexWidgetSources();
  final results = <String, Object?>{};
  group('gate', () {
    for (final name in scenarioNames) {
      testWidgets(name, (tester) async {
        binding.testTextInput.register();
        final world = PerfWorld();
        await tester.runAsync(world.seed);
        addTearDown(() async {
          await tester.runAsync(world.close);
        });
        await world.boot(tester, extraProviders: providersFor(name, world));
        await pumpFrames(tester, 10);
        await tester.runAsync(() async {
          await Future<void>.delayed(const Duration(milliseconds: 250));
        });
        final collector = PerfInstrumentation()..start(binding);
        try {
          await runScenario(tester, world, name);
          collector.endWindow();
          await tester.runAsync(() async {
            await Future<void>.delayed(const Duration(milliseconds: 250));
          });
        } finally {
          collector.stop(binding);
          await tester.pumpWidget(const SizedBox.shrink());
        }
        final score = scenarioScore(name, collector, 1000 / 60);
        results[name] = score;
        final budgetPath = Platform.environment['PERF_BUDGET_FILE'] ?? 'integration_test/perf/budgets.json';
        final budgets = jsonDecode(File(budgetPath).readAsStringSync()) as Map<String, dynamic>;
        final budget = (budgets[name] as num).toDouble();
        final p90 = (score['total_ms'] as Map<String, double>)['p90']!;
        expect(p90, lessThan(budget),
            reason: '$name: p90=$p90 ms, budget=$budget ms; '
                'frames=${score['frame_count']}, jank=${score['jank_percent']}%');
      });
    }
  });
  group('profile', () {
    testWidgets('emit scorecard even when a gate fails', (tester) async {
      final scorecard = <String, Object?>{
        'schema': 'omi-mobile-perf/v1',
        'lane': 'host_flutter_tester',
        'dataset_sizes': datasetSizes,
        'scenarios': results,
        'complete': results.length == scenarioNames.length,
      };
      await binding.traceAction(() async {
        final directory = Directory(Platform.environment['PERF_SCORECARD_DIR'] ?? '/tmp/omi-perf');
        directory.createSync(recursive: true);
        final file = File('${directory.path}/scorecard-${DateTime.now().toUtc().microsecondsSinceEpoch}.json');
        file.writeAsStringSync(const JsonEncoder.withIndent('  ').convert(scorecard));
        debugPrint('PERF_SCORECARD=${file.path}');
      }, reportKey: 'perf_trace');
      binding.reportData!['perf_scorecard'] = scorecard;
      expect(results.keys, containsAll(scenarioNames), reason: 'Scorecard must contain all four scenarios');
    });
  });
}
