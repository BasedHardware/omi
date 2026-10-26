import 'package:flutter/scheduler.dart';
import 'dart:developer' as developer;
import 'dart:ui' show FramePhase;
import 'dart:math' as math;

/// Per-scenario engine FrameTiming statistics for the profile-mode perf
/// harness. One collector instance runs for the whole test; [begin] opens a
/// named measurement window, [end] closes it and snapshots percentiles.
///
/// Windows are wall-clock driven: the caller scripts real flows and the
/// engine reports real frame timings, so numbers are comparable across builds
/// on the same physical device, not across machines (documented in the README).
class HeavyFrameCollector {
  HeavyFrameCollector({this.onEmptyWindow}) {
    SchedulerBinding.instance.addTimingsCallback(_onTimings);
  }

  final void Function(String scenario)? onEmptyWindow;

  void dispose() {
    SchedulerBinding.instance.removeTimingsCallback(_onTimings);
  }

  final _pending = <FrameTiming>[];
  final List<String> _openOrder = [];
  String? _current;
  DateTime? _openedAt;
  final Map<String, List<FrameTiming>> _windows = {};
  final Map<String, Duration> _wall = {};
  developer.TimelineTask? _task;
  int? _openedVmUs;

  void _onTimings(List<FrameTiming> timings) {
    if (_current == null) return;
    _pending.addAll(timings);
  }

  void begin(String name) {
    assert(_current == null, 'window "$_current" is still open');
    _pending.clear();
    _current = name;
    _openedAt = DateTime.now();
    _openedVmUs = developer.Timeline.now;
    _openOrder.add(name);
    _task = developer.TimelineTask()..start('heavy.$name');
  }

  Future<Map<String, Object?>> end() async {
    // FrameTiming batches can arrive up to one second after the last frame.
    // Drain before opening the next scenario, or late frames cross windows.
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    final name = _current!;
    final openedAt = _openedAt!;
    // Engine timings arrive in batches; let the last frames drain in.
    // The caller awaits a real settle before calling end(), so only a short
    // synchronous drain window remains.
    final frames = List<FrameTiming>.of(_pending);
    if (frames.isEmpty) {
      onEmptyWindow?.call(name);
      throw StateError('HEAVY_NO_ENGINE_FRAMES: $name; check native foreground state');
    }
    _windows[name] = frames;
    _wall[name] = DateTime.now().difference(openedAt);
    _current = null;
    _openedAt = null;
    _task?.finish();
    return {
      ...summarize(name, frames, _wall[name]!),
      'start_vm_us': _openedVmUs,
      'end_vm_us': developer.Timeline.now,
      'frame_timings': [
        for (final frame in frames)
          {
            'build_us': frame.buildDuration.inMicroseconds,
            'raster_us': frame.rasterDuration.inMicroseconds,
            'total_us': frame.totalSpan.inMicroseconds,
            'vsync_start_us': frame.timestampInMicroseconds(FramePhase.vsyncStart),
            'build_start_us': frame.timestampInMicroseconds(FramePhase.buildStart),
          }
      ],
      'slow_frames': [
        for (final frame in frames.where((f) => f.totalSpan.inMicroseconds > 100000).take(20))
          {
            'build_us': frame.buildDuration.inMicroseconds,
            'raster_us': frame.rasterDuration.inMicroseconds,
            'total_us': frame.totalSpan.inMicroseconds,
            'vsync_start_us': frame.timestampInMicroseconds(FramePhase.vsyncStart),
            'build_start_us': frame.timestampInMicroseconds(FramePhase.buildStart),
          }
      ],
    };
  }

  List<String> get windowOrder => List.unmodifiable(_openOrder);

  Map<String, List<FrameTiming>> get windows => _windows;

  static Map<String, Object?> summarize(String name, List<FrameTiming> frames, Duration wall) {
    int count(List<int> micros, int threshold) => micros.where((us) => us > threshold).length;
    int percentile(List<int> sorted, double p) {
      if (sorted.isEmpty) return 0;
      // Nearest rank: p90 consistently includes the worst frame for both six
      // and seven samples. The old rounded (n-1)*p switched rank at seven.
      final index = math.max(0, (sorted.length * p).ceil() - 1);
      return sorted[index];
    }

    final buildUs = frames.map((f) => f.buildDuration.inMicroseconds).toList()..sort();
    final rasterUs = frames.map((f) => f.rasterDuration.inMicroseconds).toList()..sort();
    final totalUs = frames.map((f) => f.totalSpan.inMicroseconds).toList()..sort();
    return {
      'scenario': name,
      'percentile_method': 'nearest-rank/v1',
      'frame_count': frames.length,
      'wall_ms': wall.inMilliseconds,
      'build_p50_us': percentile(buildUs, 0.50),
      'build_p90_us': percentile(buildUs, 0.90),
      'build_p99_us': percentile(buildUs, 0.99),
      'raster_p50_us': percentile(rasterUs, 0.50),
      'raster_p90_us': percentile(rasterUs, 0.90),
      'raster_p99_us': percentile(rasterUs, 0.99),
      'total_p50_us': percentile(totalUs, 0.50),
      'total_p90_us': percentile(totalUs, 0.90),
      'total_p99_us': percentile(totalUs, 0.99),
      'frames_over_16ms': count(totalUs, 16000),
      'frames_over_32ms': count(totalUs, 32000),
      'frames_over_100ms': count(totalUs, 100000),
      'worst_build_us': buildUs.isEmpty ? 0 : buildUs.last,
      'worst_raster_us': rasterUs.isEmpty ? 0 : rasterUs.last,
      'worst_total_us': totalUs.isEmpty ? 0 : totalUs.last,
    };
  }
}
