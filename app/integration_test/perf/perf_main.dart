import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'perf_budget.dart';
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
        final previousErrorBuilder = ErrorWidget.builder;
        final previousPlatform = debugDefaultTargetPlatformOverride;
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        try {
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
          final budgetPath = Platform.environment['PERF_BUDGET_FILE'] ?? 'integration_test/perf/budgets.json';
          final budgets = jsonDecode(File(budgetPath).readAsStringSync()) as Map<String, dynamic>;
          final budget = (budgets['_gate'] as Map<String, dynamic>)[name] as Map<String, dynamic>;
          final violations = budgetViolations(collector, budget);
          score['gate_violations'] = violations;
          results[name] = score;
          debugPrint(
              'PERF $name frames=${collector.sampledFrames} work=${collector.workCounts} violations=$violations');
          expect(violations, isEmpty, reason: '$name: ${violations.join('; ')}');
        } finally {
          await tester.pumpWidget(const SizedBox.shrink());
          ErrorWidget.builder = previousErrorBuilder;
          debugDefaultTargetPlatformOverride = previousPlatform;
        }
      }, semanticsEnabled: false);
    }
  });
  group('profile', () {
    testWidgets('emit scorecard even when a gate fails', (tester) async {
      final scorecard = <String, Object?>{
        'schema': 'omi-mobile-perf/v2',
        'lane': 'host_flutter_tester',
        'source_sha': Platform.environment['PERF_SOURCE_SHA'],
        'dataset_sizes': datasetSizes,
        'shell': 'source_checked_production_ios_analytics',
        'gate': 'deterministic_work_and_semantics_share',
        'scenarios': results,
        'complete': results.length == scenarioNames.length,
      };
      final directory = Directory(Platform.environment['PERF_SCORECARD_DIR'] ?? '/tmp/omi-perf');
      directory.createSync(recursive: true);
      final file = File('${directory.path}/scorecard-${DateTime.now().toUtc().microsecondsSinceEpoch}.json');
      file.writeAsStringSync(const JsonEncoder.withIndent('  ').convert(scorecard));
      debugPrint('PERF_SCORECARD=${file.path}');
      binding.reportData ??= <String, dynamic>{};
      binding.reportData!['perf_scorecard'] = scorecard;
      expect(results.keys, containsAll(scenarioNames), reason: 'Scorecard must contain all scenarios');
    }, semanticsEnabled: false);
  });
}
