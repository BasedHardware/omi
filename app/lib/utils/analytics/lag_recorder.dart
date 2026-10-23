import 'dart:async';
import 'dart:collection';
import 'dart:developer' show Timeline;
import 'dart:ui' show FramePhase, FrameTiming;

import 'package:flutter/gestures.dart' show kTouchSlop;
import 'package:flutter/widgets.dart';

/// Page labels for routes pushed through `routeToPage`, read by [LagRecorder].
/// Widget type names are code identifiers, never user content, and they only
/// reach the local debug log.
final Expando<String> lagRouteLabels = Expando<String>('lag_route_label');

/// Where the user was and what they were doing when a frame was produced.
enum LagInteraction { idle, scroll, tap }

typedef LagEmitter = void Function(String type, Map<String, Object?> fields);

/// Local lag recorder for real devices (release and TestFlight builds).
///
/// Host `flutter test` cannot raster and cannot reproduce production iOS
/// conditions, so this records what the device actually did: every frame's
/// UI-thread (build) and raster-thread time, which surface it belonged to,
/// whether the user was scrolling or had just tapped, tap-to-frame latency, and
/// UI-isolate stalls between frames. It writes to the local debug log only,
/// behind Settings → Developer → Debug logs; nothing is sent anywhere.
///
/// Thresholds are fixed so captures compare across devices: a frame is slow
/// when either thread took over 16.7 ms, severe over 33.3 ms, a freeze over
/// 100 ms. Per frame it costs a few integer comparisons; only severe frames,
/// slow taps and stalls allocate.
class LagRecorder {
  LagRecorder({
    required this.emit,
    this.watchdogPeriod = const Duration(milliseconds: 250),
    int Function()? nowUs,
    DateTime Function()? wallClock,
  })  : _nowUs = nowUs ?? (() => Timeline.now),
        _wallClock = wallClock ?? DateTime.now;

  static const int slowUs = 16667;
  static const int severeUs = 33333;
  static const int freezeUs = 100000;
  static const int stallThresholdUs = 100000;
  static const int slowTapUs = 100000;

  /// Severe frames logged one by one, per rolling minute. Every frame still counts in the summaries.
  static const int frameLogsPerMinute = 20;
  static const int _worstKept = 12;
  static const int _maxSurfaces = 40;

  final LagEmitter emit;
  final Duration watchdogPeriod;
  final int Function() _nowUs;
  final DateTime Function() _wallClock;

  final Map<String, _SurfaceStats> _surfaces = {};
  final ListQueue<_SurfaceMark> _surfaceMarks = ListQueue();
  final ListQueue<_Span> _scrolls = ListQueue();
  final List<Map<String, Object?>> _worstFrames = [];
  final List<Map<String, Object?>> _worstStalls = [];
  final List<Map<String, Object?>> _slowestTaps = [];
  final ListQueue<int> _frameLogTimes = ListQueue();

  String _surface = 'launch';
  int _scrollDepth = 0;
  int? _scrollStartUs;
  int? _lastTapUs;
  int? _pointerDownUs;
  bool _pointerMoved = false;
  Offset? _pointerDownAt;
  Timer? _watchdog;
  Stopwatch? _watchdogClock;
  int _tapGeneration = 0;

  String get surface => _surface;

  /// The page or tab the next frames belong to.
  void setSurface(String surface) {
    if (surface == _surface) return;
    _surface = surface;
    _surfaceMarks.addLast(_SurfaceMark(_nowUs(), surface));
    while (_surfaceMarks.length > 16) {
      _surfaceMarks.removeFirst();
    }
  }

  // ---- input context ------------------------------------------------------

  void onScrollStart() {
    if (_scrollDepth++ == 0) _scrollStartUs = _nowUs();
  }

  void onScrollEnd() {
    if (_scrollDepth == 0) return;
    if (--_scrollDepth > 0) return;
    // Frames up to 150 ms after the finger lifts still belong to the gesture.
    _scrolls.addLast(_Span(_scrollStartUs ?? _nowUs(), _nowUs() + 150000));
    while (_scrolls.length > 8) {
      _scrolls.removeFirst();
    }
    _scrollStartUs = null;
  }

  void onPointerDown(Offset position) {
    _pointerDownUs = _nowUs();
    _pointerDownAt = position;
    _pointerMoved = false;
  }

  void onPointerMove(Offset position) {
    final start = _pointerDownAt;
    if (start != null && (position - start).distance > kTouchSlop) _pointerMoved = true;
  }

  /// A pointer lifted without travelling: a tap. Times it to the end of the
  /// next frame's UI work, which includes the tap handler's own synchronous
  /// work (this listener sits above the gesture arena, so it runs first).
  void onPointerUp() {
    final downUs = _pointerDownUs;
    _pointerDownUs = null;
    if (downUs == null || _pointerMoved || _scrollDepth > 0) return;
    final upUs = _nowUs();
    _lastTapUs = upUs;
    final generation = ++_tapGeneration;
    final surfaceAtTap = _surface;
    final watch = Stopwatch()..start();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final us = watch.elapsedMicroseconds;
      // A newer tap supersedes this one; its own callback reports it.
      if (generation != _tapGeneration) return;
      recordTap(surfaceAtTap, us);
    });
  }

  @visibleForTesting
  void recordTap(String surfaceAtTap, int us) {
    // A tap that changes nothing on screen waits for an unrelated frame; ignore those.
    if (us > 2000000) return;
    final stats = _stats(surfaceAtTap);
    stats.taps++;
    if (us > stats.worstTapUs) stats.worstTapUs = us;
    if (us < slowTapUs) return;
    stats.slowTaps++;
    final record = {'at': _wallClock().toIso8601String(), 'surface': surfaceAtTap, 'tap_to_frame_ms': _ms(us)};
    _keepWorst(_slowestTaps, record, 'tap_to_frame_ms');
    _emit('mobile_lag_tap', record);
  }

  // ---- frames ---------------------------------------------------------------

  void observeTimings(List<FrameTiming> timings) {
    for (final t in timings) {
      observeFrame(
        buildUs: t.buildDuration.inMicroseconds,
        rasterUs: t.rasterDuration.inMicroseconds,
        totalUs: t.totalSpan.inMicroseconds,
        vsyncStartUs: t.timestampInMicroseconds(FramePhase.vsyncStart),
      );
    }
  }

  @visibleForTesting
  void observeFrame({required int buildUs, required int rasterUs, required int totalUs, int? vsyncStartUs}) {
    final at = vsyncStartUs ?? _nowUs();
    final surface = _surfaceAt(at);
    final stats = _stats(surface);
    final interaction = _interactionAt(at);
    stats.frames++;
    stats.buildUs += buildUs;
    stats.rasterUs += rasterUs;
    final worst = buildUs > rasterUs ? buildUs : rasterUs;
    if (worst <= slowUs) return;

    stats.slow++;
    stats.slowBy[interaction.index]++;
    if (buildUs >= rasterUs) {
      stats.buildBound++;
    } else {
      stats.rasterBound++;
    }
    if (worst > severeUs) stats.severe++;
    if (worst > freezeUs) stats.freezes++;
    if (worst > stats.worstUs) stats.worstUs = worst;
    if (worst <= severeUs) return;

    final record = <String, Object?>{
      'at': _wallClock().toIso8601String(),
      'surface': surface,
      'interaction': interaction.name,
      'build_ms': _ms(buildUs),
      'raster_ms': _ms(rasterUs),
      'total_ms': _ms(totalUs),
      'bound': buildUs >= rasterUs ? 'build' : 'raster',
    };
    _keepWorst(_worstFrames, record, 'worst_ms', worst);
    if (_frameLogAllowed()) _emit('mobile_lag_frame', record);
  }

  // ---- UI-isolate stalls ------------------------------------------------------

  /// Starts the stall watchdog: a timer that notices when the UI isolate was
  /// blocked (JSON decode, sorting, sync I/O) even between frames.
  void startWatchdog() {
    if (_watchdog != null) return;
    _watchdogClock = Stopwatch()..start();
    _watchdog = Timer.periodic(watchdogPeriod, (_) => _tick());
  }

  void stopWatchdog() {
    _watchdog?.cancel();
    _watchdog = null;
    _watchdogClock = null;
  }

  bool get watchdogRunning => _watchdog != null;

  void _tick() {
    final clock = _watchdogClock;
    if (clock == null) return;
    final elapsed = clock.elapsedMicroseconds;
    clock.reset();
    recordStall(elapsed - watchdogPeriod.inMicroseconds);
  }

  @visibleForTesting
  void recordStall(int lateUs) {
    if (lateUs < stallThresholdUs) return;
    final stats = _stats(_surface);
    stats.stalls++;
    if (lateUs > stats.worstStallUs) stats.worstStallUs = lateUs;
    final record = {
      'at': _wallClock().toIso8601String(),
      'surface': _surface,
      'interaction': _interactionAt(_nowUs()).name,
      'blocked_ms': _ms(lateUs),
    };
    _keepWorst(_worstStalls, record, 'blocked_ms');
    _emit('mobile_lag_stall', record);
  }

  // ---- output -------------------------------------------------------------

  int get framesSinceReport => _surfaces.values.fold<int>(0, (a, s) => a + s.frames);

  /// The capture: worst frames, stalls and taps since the last report, plus
  /// per-surface summaries. Written when the app goes to the background and
  /// every few minutes in the foreground.
  void writeReport(String reason) {
    final frames = framesSinceReport;
    if (frames == 0 && _worstStalls.isEmpty && _slowestTaps.isEmpty) return;
    final ranked = _surfaces.entries.toList()..sort((a, b) => b.value.slow.compareTo(a.value.slow));
    _emit('mobile_lag_report', {
      'reason': reason,
      'frames': frames,
      'surfaces': [
        for (final e in ranked.take(12)) {'surface': e.key, ...e.value.toJson()}
      ],
      'worst_frames': List.of(_worstFrames),
      'worst_stalls': List.of(_worstStalls),
      'slowest_taps': List.of(_slowestTaps),
    });
    _worstFrames.clear();
    _worstStalls.clear();
    _slowestTaps.clear();
    _surfaces.clear();
  }

  // ---- internals ------------------------------------------------------------

  _SurfaceStats _stats(String surface) {
    final existing = _surfaces[surface];
    if (existing != null) return existing;
    if (_surfaces.length >= _maxSurfaces) return _surfaces.putIfAbsent('other', _SurfaceStats.new);
    return _surfaces[surface] = _SurfaceStats();
  }

  String _surfaceAt(int us) {
    // Timings arrive in batches up to a second late; attribute each frame to
    // the surface that was on top when it started.
    for (final mark in _surfaceMarks.toList().reversed) {
      if (mark.us <= us) return mark.surface;
    }
    return _surfaceMarks.isEmpty ? _surface : 'launch';
  }

  LagInteraction _interactionAt(int us) {
    final start = _scrollStartUs;
    if (_scrollDepth > 0 && start != null && us >= start) return LagInteraction.scroll;
    for (final span in _scrolls) {
      if (us >= span.start && us <= span.end) return LagInteraction.scroll;
    }
    final tap = _lastTapUs;
    if (tap != null && us >= tap && us - tap <= 1000000) return LagInteraction.tap;
    return LagInteraction.idle;
  }

  bool _frameLogAllowed() {
    final now = _nowUs();
    while (_frameLogTimes.isNotEmpty && now - _frameLogTimes.first > 60000000) {
      _frameLogTimes.removeFirst();
    }
    if (_frameLogTimes.length >= frameLogsPerMinute) return false;
    _frameLogTimes.addLast(now);
    return true;
  }

  void _keepWorst(List<Map<String, Object?>> list, Map<String, Object?> record, String key, [int? scoreUs]) {
    final score = scoreUs != null ? scoreUs / 1000 : (record[key] as num).toDouble();
    final entry = {...record, '_score': score};
    if (list.length >= _worstKept && (list.last['_score'] as double) >= score) return;
    list.add(entry);
    list.sort((a, b) => (b['_score'] as double).compareTo(a['_score'] as double));
    if (list.length > _worstKept) list.removeLast();
  }

  void _emit(String type, Map<String, Object?> fields) {
    try {
      emit(type, {
        for (final e in fields.entries)
          if (e.key != '_score') e.key: e.value is List ? _strip(e.value as List) : e.value,
      });
    } catch (_) {}
  }

  static List<Object?> _strip(List list) => [
        for (final item in list)
          item is Map<String, Object?>
              ? {
                  for (final e in item.entries)
                    if (e.key != '_score') e.key: e.value
                }
              : item,
      ];

  static double _ms(int us) => (us / 100).round() / 10;
}

class _SurfaceStats {
  int frames = 0;
  int slow = 0;
  int severe = 0;
  int freezes = 0;
  int buildBound = 0;
  int rasterBound = 0;
  int worstUs = 0;
  int buildUs = 0;
  int rasterUs = 0;
  int taps = 0;
  int slowTaps = 0;
  int worstTapUs = 0;
  int stalls = 0;
  int worstStallUs = 0;
  final List<int> slowBy = List<int>.filled(LagInteraction.values.length, 0);

  Map<String, Object?> toJson() => {
        'frames': frames,
        'slow_frames': slow,
        'severe_frames': severe,
        'freezes': freezes,
        'build_bound': buildBound,
        'raster_bound': rasterBound,
        'slow_while_scrolling': slowBy[LagInteraction.scroll.index],
        'slow_after_tap': slowBy[LagInteraction.tap.index],
        'slow_idle': slowBy[LagInteraction.idle.index],
        'worst_frame_ms': LagRecorder._ms(worstUs),
        'mean_build_ms': frames == 0 ? 0 : LagRecorder._ms(buildUs ~/ frames),
        'mean_raster_ms': frames == 0 ? 0 : LagRecorder._ms(rasterUs ~/ frames),
        'taps': taps,
        'slow_taps': slowTaps,
        'worst_tap_ms': LagRecorder._ms(worstTapUs),
        'stalls': stalls,
        'worst_stall_ms': LagRecorder._ms(worstStallUs),
      };
}

class _SurfaceMark {
  _SurfaceMark(this.us, this.surface);
  final int us;
  final String surface;
}

class _Span {
  _Span(this.start, this.end);
  final int start;
  final int end;
}

/// Feeds scroll and pointer context to a [LagRecorder]. Mount once above the
/// navigator; it never consumes a notification or an event.
class LagInputScope extends StatelessWidget {
  const LagInputScope({super.key, required this.recorder, required this.child});

  final LagRecorder? recorder;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final recorder = this.recorder;
    if (recorder == null) return child;
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (e) => recorder.onPointerDown(e.position),
      onPointerMove: (e) => recorder.onPointerMove(e.position),
      onPointerUp: (_) => recorder.onPointerUp(),
      child: NotificationListener<ScrollNotification>(
        onNotification: (n) {
          if (n is ScrollStartNotification) recorder.onScrollStart();
          if (n is ScrollEndNotification) recorder.onScrollEnd();
          return false;
        },
        child: child,
      ),
    );
  }
}
