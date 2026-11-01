import 'dart:io';
import 'perf_instrumentation.dart';

final _widgetSources = <String, List<String>>{};
void indexWidgetSources() {
  if (_widgetSources.isNotEmpty) return;
  for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
    if (!file.path.endsWith('.dart') || file.path.endsWith('.g.dart')) continue;
    for (final match in RegExp(r'class\s+(\w+)').allMatches(file.readAsStringSync())) {
      (_widgetSources[match[1]!] ??= []).add(file.path);
    }
  }
}

List<String> sourcesFor(String type) => _widgetSources[type.split('<').first] ?? const [];

Map<String, Object?> scenarioScore(String name, PerfInstrumentation sample, double frameBudgetMs) {
  // Report the UI pipeline on host: engine callbacks are not reliably available
  // under virtual time. Never substitute synthetic zero-duration frames.
  final build = sample.uiMs;
  final top = sample.rebuilds.entries.toList()
    ..sort((a, b) {
      final byCount = b.value.compareTo(a.value);
      return byCount != 0 ? byCount : a.key.compareTo(b.key);
    });
  final jank = build.where((ms) => ms > frameBudgetMs).length;
  final engineBuild = sample.timings.map((t) => t.buildDuration.inMicroseconds / 1000).toList();
  final raster = sample.timings.map((t) => t.rasterDuration.inMicroseconds / 1000).toList();
  final total = [for (var i = 0; i < raster.length; i++) engineBuild[i] + raster[i]];
  var buildBound = 0;
  var rasterBound = 0;
  for (var i = 0; i < total.length; i++) {
    if (total[i] <= frameBudgetMs) continue;
    if (engineBuild[i] >= raster[i]) {
      buildBound++;
    } else {
      rasterBound++;
    }
  }
  return {
    'scenario': name,
    'measurement': 'host_pipeline_work_counts_with_wall_clock_diagnostics',
    'frame_count': build.length,
    'idle_frames_excluded': sample.idleFrames,
    'build_ms': quantiles(build),
    'raster_ms': null,
    'total_ms': quantiles(build),
    'jank_threshold_ms': frameBudgetMs,
    'jank_count': jank,
    'jank_percent': 100 * jank / build.length,
    'janky_frame_split': {'build_bound': jank, 'raster_bound': null},
    'top_rebuilders': [
      for (final e in top.take(10))
        {'widget': e.key, 'count': e.value, 'initial_builds': sample.initialBuilds[e.key] ?? 0}
    ],
    'top_app_rebuilders': [
      for (final e in top.where((e) => sourcesFor(e.key).isNotEmpty).take(10))
        {'widget': e.key, 'count': e.value, 'source_files': sourcesFor(e.key)}
    ],
    'rebuilders_by_widget': sample.rebuilds,
    'semantics_enabled': sample.semanticsEnabled,
    'ui_phase_ms': sample.phaseMs,
    'ui_phase_counts': sample.phaseCounts,
    'sampled_frames': sample.sampledFrames,
    'semantics_compiles_per_frame':
        sample.sampledFrames == 0 ? null : (sample.phaseCounts['SEMANTICS'] ?? 0) / sample.sampledFrames,
    'work_counts': sample.workCounts,
    'ui_phase_shares': {
      for (final phase in sample.phaseMs.entries)
        phase.key: sample.phaseMs.values.fold<double>(0, (a, b) => a + b) == 0
            ? 0.0
            : phase.value / sample.phaseMs.values.fold<double>(0, (a, b) => a + b),
    },
    'layer_census_max': sample.maxLayers,
    'painted_image_decode_sizes': sample.images,
    'save_layer_count': null,
    'save_layer_status': 'requires device GPU trace; layer census is not a saveLayer count',
    'ticker_census': {
      'method': 'scheduler_transient_callbacks_proxy',
      'max_concurrent': sample.animationCallbacks.fold<int>(0, (a, b) => a > b ? a : b),
      'frames_with_overlap': sample.animationCallbacks.where((n) => n > 1).length,
      'samples': sample.animationCallbacks,
    },
    'raw_ui_frame_ms': build,
    'janky_frames': [
      for (var i = 0; i < build.length; i++)
        if (build[i] > frameBudgetMs)
          {
            'frame_index': i,
            'ui_ms': build[i],
            'classification': 'ui_bound',
            'rebuilders': sample.frameRebuilders[i],
            'animation_callbacks': sample.animationCallbacks[i]
          }
    ],
    'engine_frame_timing': {
      'frame_count': total.length,
      'build_ms': total.isEmpty ? null : quantiles(engineBuild),
      'raster_ms': total.isEmpty ? null : quantiles(raster),
      'total_ms': total.isEmpty ? null : quantiles(total),
      'janky_frame_split': {'build_bound': buildBound, 'raster_bound': rasterBound},
    },
  };
}
