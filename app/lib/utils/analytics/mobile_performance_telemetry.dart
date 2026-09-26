import 'dart:ui';

import 'package:flutter/widgets.dart';

typedef PerformanceEmitter = void Function(String name, Map<String, dynamic> properties);

/// Bounded aggregates of Flutter frames. These measure rendering, not network
/// readiness, native hangs, battery use, or whether content was useful.
class MobilePerformanceTelemetry extends NavigatorObserver {
  MobilePerformanceTelemetry({required this.emit, required this.identityEpoch});

  final PerformanceEmitter emit;
  final int Function() identityEpoch;
  int _epoch = 0;
  int _frames = 0;
  int _slowFrames = 0;
  int _maxFrameUs = 0;
  int _generation = 0;
  bool _attached = false;
  bool _foreground = true;
  String _surface = 'launch';

  void attach() {
    if (_attached) return;
    _attached = true;
    WidgetsBinding.instance.addTimingsCallback(_timings);
    _begin('launch');
  }

  void dispose() {
    flush();
    _generation++;
    if (_attached) WidgetsBinding.instance.removeTimingsCallback(_timings);
    _attached = false;
  }

  void setForeground(bool value) {
    flush();
    _foreground = value;
    _generation++;
    _epoch = identityEpoch();
  }

  @override
  void didChangeTop(Route<dynamic> topRoute, Route<dynamic>? previousTopRoute) {
    final name = topRoute.settings.name;
    // Never transmit dynamic routes, query strings, or runtime type names.
    _begin(const {'/', '/home', '/chat', '/settings', '/onboarding', '/conversations', '/tasks'}.contains(name)
        ? name!
        : 'unnamed_route');
  }

  void _begin(String surface) {
    flush();
    _surface = surface;
    _epoch = identityEpoch();
    final epoch = _epoch;
    final generation = ++_generation;
    final watch = Stopwatch()..start();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_foreground || generation != _generation || epoch != identityEpoch()) return;
      _send('Mobile Render Observation', {
        'surface': surface,
        'stage': 'first_frame',
        'duration_ms': watch.elapsedMilliseconds,
      });
    });
  }

  void _timings(List<FrameTiming> timings) {
    if (!_foreground) return;
    if (_epoch != identityEpoch()) {
      _frames = _slowFrames = _maxFrameUs = 0;
      _epoch = identityEpoch();
    }
    for (final frame in timings) {
      observeFrame(frame.totalSpan.inMicroseconds);
    }
  }

  @visibleForTesting
  void observeFrame(int totalMicroseconds) {
    if (!_foreground || totalMicroseconds < 0) return;
    _frames++;
    // Fixed, documented threshold allows comparisons across refresh rates;
    // it is not labeled a device-vsync missed-frame count.
    if (totalMicroseconds > 32000) _slowFrames++;
    if (totalMicroseconds > _maxFrameUs) _maxFrameUs = totalMicroseconds;
    if (_frames >= 600) flush();
  }

  void flush() {
    if (_frames > 0 && _epoch == identityEpoch()) {
      _send('Mobile Render Observation', {
        'surface': _surface,
        'stage': 'frame_summary',
        'frame_count': _frames,
        'frames_over_32ms': _slowFrames,
        'max_frame_us': _maxFrameUs,
      });
    }
    _frames = _slowFrames = _maxFrameUs = 0;
  }

  void _send(String name, Map<String, dynamic> properties) {
    try {
      emit(name, properties);
    } catch (_) {}
  }
}
