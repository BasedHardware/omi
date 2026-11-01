import 'perf_instrumentation.dart';

/// Host admission uses work, never elapsed host time. Missing evidence fails.
List<String> budgetViolations(PerfInstrumentation sample, Map<String, dynamic> budget) {
  final failures = <String>[];
  if (sample.sampledFrames == 0 || (sample.phaseCounts['LAYOUT'] ?? 0) == 0) {
    failures.add('No measured pipeline frames; do not accept an empty scenario');
  }
  if (sample.layouts == 0 || sample.paints == 0 || sample.rebuilds.isEmpty) {
    failures.add('Missing layout/paint/rebuild instrumentation; an empty or profile-mode host sample is not admission');
  }
  if (sample.semanticsEnabled) {
    failures.add('Semantics enabled without an accessibility client: release wrapper leaked a handle');
  }
  final frames = sample.sampledFrames;
  for (final entry in (budget['counts'] as Map<String, dynamic>).entries) {
    final measured = sample.workCounts[entry.key];
    if (measured == null || measured > (entry.value as num)) {
      failures.add(
          '${entry.key}=$measured exceeds ${entry.value}; remove added per-frame/list work; never raise budgets to pass');
    }
  }
  final semanticsPerFrame = frames == 0 ? double.infinity : (sample.phaseCounts['SEMANTICS'] ?? 0) / frames;
  if (semanticsPerFrame > (budget['semantics_compiles_per_frame'] as num)) {
    failures.add('semantics_compiles_per_frame=$semanticsPerFrame exceeds ${budget['semantics_compiles_per_frame']}');
  }
  final total = sample.phaseMs.values.fold<double>(0, (a, b) => a + b);
  if (total <= 0) failures.add('No pipeline phase timings; instrumentation unavailable');
  for (final entry in (budget['phase_shares'] as Map<String, dynamic>).entries) {
    final share = total <= 0 ? double.infinity : (sample.phaseMs[entry.key] ?? 0) / total;
    if (share > (entry.value as num)) failures.add('${entry.key} share=$share exceeds ${entry.value}');
  }
  return failures;
}
