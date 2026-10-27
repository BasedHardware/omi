import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'perf_budget.dart';
import 'perf_instrumentation.dart';
import 'perf_scenarios.dart';
import 'perf_scorecard.dart';

/// Virtual frame time makes counts deterministic; the fixture still needs real
/// loopback HTTP, which the ordinary widget binding disables by default.
class _PerfHostBinding extends AutomatedTestWidgetsFlutterBinding {
  @override
  bool get overrideHttpClient => false;
}

_PerfHostBinding? _hostBinding;

void main() {
  final binding = _hostBinding ??= _PerfHostBinding();
  final testFailures = <String>[];
  late TestExceptionReporter previousReporter;
  setUpAll(() {
    previousReporter = reportTestException;
    reportTestException = (details, description) {
      testFailures.add(details.toString());
      previousReporter(details, description);
    };
  });
  tearDownAll(() => reportTestException = previousReporter);
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
          try {
            await tester.pumpWidget(const SizedBox.shrink());
            await drainFixtureIo(tester);
            // Close pooled HTTP idle-connection timers outside the measured
            // window; any still-hung request remains a real test failure.
            await tester.pump(const Duration(seconds: 31));
          } finally {
            ErrorWidget.builder = previousErrorBuilder;
            debugDefaultTargetPlatformOverride = previousPlatform;
          }
        }
      }, semanticsEnabled: false);
    }
  });
  group('scorecard', () {
    testWidgets('emit scorecard even when a gate fails', (tester) async {
      final scorecard = <String, Object?>{
        'schema': 'omi-mobile-perf/v2',
        'lane': 'host_flutter_tester',
        'source_sha': Platform.environment['PERF_SOURCE_SHA'],
        'dataset_sizes': datasetSizes,
        'shell': 'source_checked_production_ios_analytics',
        'gate': 'deterministic_work_and_semantics_share',
        'scenarios': results,
        'test_failure_count': testFailures.length,
        'test_failures': [
          for (final failure in testFailures) failure.length > 2000 ? failure.substring(0, 2000) : failure
        ],
        'complete': results.length == scenarioNames.length && testFailures.isEmpty,
      };
      final directory = Directory(Platform.environment['PERF_SCORECARD_DIR'] ?? '/tmp/omi-perf');
      directory.createSync(recursive: true);
      final file = File('${directory.path}/scorecard-${DateTime.now().toUtc().microsecondsSinceEpoch}.json');
      file.writeAsStringSync(const JsonEncoder.withIndent('  ').convert(scorecard));
      debugPrint('PERF_SCORECARD=${file.path}');
      expect(results.keys, containsAll(scenarioNames), reason: 'Scorecard must contain all scenarios');
    }, semanticsEnabled: false);
  });
}
