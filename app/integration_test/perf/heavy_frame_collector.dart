import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/scheduler.dart';
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
  HeavyStallProbe? _stalls;

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
    _stalls = HeavyStallProbe()..start();
  }

  Future<Map<String, Object?>> end() async {
    // Stalls belong to the scripted flow, not to the frame drain below.
    final stalls = _stalls!.stop();
    _stalls = null;
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
      ...stalls,
      'start_vm_us': _openedVmUs,
      'end_vm_us': developer.Timeline.now,
      'frame_timings': [
        for (final frame in frames)
          {
            'build_us': frame.buildDuration.inMicroseconds,
            'raster_us': frame.rasterDuration.inMicroseconds,
            'total_us': frameTotalUs(frame),
            'vsync_start_us': frame.timestampInMicroseconds(FramePhase.vsyncStart),
            'build_start_us': frame.timestampInMicroseconds(FramePhase.buildStart),
          }
      ],
      'slow_frames': [
        for (final frame in frames.where((f) => frameTotalUs(f) > 100000).take(20))
          {
            'build_us': frame.buildDuration.inMicroseconds,
            'raster_us': frame.rasterDuration.inMicroseconds,
            'total_us': frameTotalUs(frame),
            'vsync_start_us': frame.timestampInMicroseconds(FramePhase.vsyncStart),
            'build_start_us': frame.timestampInMicroseconds(FramePhase.buildStart),
          }
      ],
    };
  }

  /// Raster finish minus the earlier of vsync and build start. On iOS 27 (iPhone 15 Pro Max) a
  /// frame the framework schedules outside the vsync callback can start building ~1 ms before its
  /// recorded vsync, and [FrameTiming.totalSpan] (raster finish - vsync) then goes negative.
  static int frameTotalUs(FrameTiming frame) =>
      frame.timestampInMicroseconds(FramePhase.rasterFinish) -
      math.min(
          frame.timestampInMicroseconds(FramePhase.vsyncStart), frame.timestampInMicroseconds(FramePhase.buildStart));

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
    final totalUs = frames.map((f) => frameTotalUs(f)).toList()..sort();
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

/// Main-isolate stalls inside a window, the field lag watchdog's view: a short periodic timer
/// whose late ticks measure how long the event loop was blocked. A stall while the screen is idle
/// draws no frame, so frame timings alone never see it.
class HeavyStallProbe {
  static const tick = Duration(milliseconds: 20);

  final _clock = Stopwatch();
  final _stalls = <int>[];
  Timer? _timer;
  int _lastUs = 0;

  void start() {
    _clock.start();
    _lastUs = 0;
    _timer = Timer.periodic(tick, (_) => record(_clock.elapsedMicroseconds));
  }

  /// One tick observed at [nowUs]; anything beyond the tick period is blocked time.
  void record(int nowUs) {
    final lateUs = nowUs - _lastUs - tick.inMicroseconds;
    _lastUs = nowUs;
    if (lateUs >= 50000) _stalls.add(lateUs);
  }

  Map<String, Object?> stop() {
    _timer?.cancel();
    _timer = null;
    return summarize(_stalls);
  }

  static Map<String, Object?> summarize(List<int> stallsUs) {
    final over100 = stallsUs.where((us) => us >= 100000).toList();
    return {
      'stalls_over_50ms': stallsUs.length,
      'stalls_over_100ms': over100.length,
      'stall_blocked_over_100ms_us': over100.fold<int>(0, (sum, us) => sum + us),
      'worst_stall_us': stallsUs.fold<int>(0, math.max),
    };
  }
}
