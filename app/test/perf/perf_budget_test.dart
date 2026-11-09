import 'package:flutter_test/flutter_test.dart';
import '../../integration_test/perf/perf_budget.dart';
import '../../integration_test/perf/perf_instrumentation.dart';

void main() {
  final budget = <String, dynamic>{
    'counts': {'rebuilds': 10, 'semantics_compiles': 0},
    'semantics_compiles_per_frame': 0,
    'phase_shares': {'SEMANTICS': 0},
  };
  PerfInstrumentation sample() => PerfInstrumentation()
    ..sampledFrames = 10
    ..layouts = 10
    ..paints = 10
    ..phaseCounts.addAll({'LAYOUT': 10, 'SEMANTICS': 0})
    ..phaseMs.addAll({'LAYOUT': 10, 'SEMANTICS': 0})
    ..rebuilds['row'] = 10;

  test('counts stay green when host timing is arbitrarily inflated', () {
    final clean = sample()..phaseMs['LAYOUT'] = 1000000;
    expect(budgetViolations(clean, budget), isEmpty);
  });
  test('a held semantics mutation fails both work and share budgets', () {
    final mutation = sample()
      ..semanticsEnabled = true
      ..phaseCounts['SEMANTICS'] = 10
      ..phaseMs['SEMANTICS'] = 3;
    expect(budgetViolations(mutation, budget).join('\n'), contains('Semantics enabled'));
    expect(budgetViolations(mutation, budget).join('\n'), contains('SEMANTICS share='));
  });
  test('extra per-frame rebuilds fail admission', () {
    expect(budgetViolations(sample()..rebuilds['wrapper'] = 10, budget).join('\n'), contains('rebuilds=20'));
  });
  test('empty samples cannot go green', () {
    expect(budgetViolations(PerfInstrumentation(), budget), isNotEmpty);
  });
}
