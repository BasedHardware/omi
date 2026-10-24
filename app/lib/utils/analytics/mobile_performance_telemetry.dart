import 'dart:ui';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:omi/utils/analytics/lag_recorder.dart';

typedef PerformanceEmitter = void Function(String name, Map<String, dynamic> properties);

/// Bounded aggregates of Flutter frames. These measure rendering, not network
/// readiness, native hangs, battery use, or whether content was useful.
class MobilePerformanceTelemetry extends NavigatorObserver {
  MobilePerformanceTelemetry({
    required this.emit,
    required this.identityEpoch,
    this.diagnosticsEnabled,
    LagRecorder? lag,
  }) : _lagOverride = lag;

  final PerformanceEmitter emit;
  final int Function() identityEpoch;

  /// Explicit local-diagnostics switch. Routine PostHog emission is removed.
  /// Null and false both stay silent; only an explicit true enables the
  /// bounded local path.
  final bool Function()? diagnosticsEnabled;

  /// Local lag capture, active only while [diagnosticsEnabled] is true. It
  /// writes through [emit] like the render observations, so main.dart's
  /// existing wiring carries it; each event names itself in its `event` field.
  late final LagRecorder lag = _lagOverride ?? LagRecorder(emit: _send);
  final LagRecorder? _lagOverride;
  bool _lagActive = false;
  int _homeTab = 0;
  Route<dynamic>? _top;
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
    // Global route: sees every pointer without a widget in the tree, and runs
    // before the gesture arena sweep that fires onTap.
    GestureBinding.instance.pointerRouter.addGlobalRoute(_onPointer);
    lagHomeTabChanged = setHomeTab;
    _begin('launch');
    _refreshLag();
  }

  void _onPointer(PointerEvent event) {
    if (!_lagActive) return;
    switch (event) {
      case PointerDownEvent():
        lag.onPointerDown(event.pointer, event.position);
      case PointerMoveEvent():
        lag.onPointerMove(event.pointer, event.position);
      case PointerUpEvent():
        lag.onPointerUp(event.pointer);
      case PointerCancelEvent():
        lag.onPointerCancel(event.pointer);
      default:
        break;
    }
  }

  void dispose() {
    flush();
    lag.stopWatchdog();
    lag.active = false;
    _generation++;
    if (_attached) {
      WidgetsBinding.instance.removeTimingsCallback(_timings);
      GestureBinding.instance.pointerRouter.removeGlobalRoute(_onPointer);
      if (lagHomeTabChanged == setHomeTab) lagHomeTabChanged = null;
    }
    _attached = false;
  }

  void setForeground(bool value) {
    flush();
    if (!value && _lagActive) lag.writeReport('background');
    _foreground = value;
    _generation++;
    _epoch = identityEpoch();
    _refreshLag();
  }

  /// The Home shell switches tabs without a route change.
  void setHomeTab(int tab) {
    if (tab == _homeTab) return;
    _homeTab = tab;
    final top = _top;
    if (top != null) lag.setSurface(lagSurfaceFor(top, homeTab: _homeTab));
  }

  void _refreshLag() {
    final recorder = lag;
    _lagActive = _attached && _foreground && diagnosticsEnabled?.call() == true;
    recorder.active = _lagActive;
    if (_lagActive) {
      recorder.startWatchdog();
    } else {
      recorder.stopWatchdog();
    }
  }

  @override
  void didChangeTop(Route<dynamic> topRoute, Route<dynamic>? previousTopRoute) {
    _top = topRoute;
    _refreshLag();
    lag.setSurface(lagSurfaceFor(topRoute, homeTab: _homeTab));
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
    if (_lagActive) {
      final recorder = lag;
      recorder.observeTimings(timings);
      // About five minutes of frames at 60 Hz: keep a capture even if the app never backgrounds.
      if (recorder.framesSinceReport >= 18000) recorder.writeReport('periodic');
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
    if (diagnosticsEnabled?.call() != true) return;
    try {
      emit(name, properties);
    } catch (_) {}
  }
}

/// A local-only label for the page on top: the pushed page's widget type for
/// `routeToPage` pushes, the Home tab for the root route, otherwise the kind of
/// route. Never contains route arguments or content.
String lagSurfaceFor(Route<dynamic> route, {required int homeTab}) {
  final label = lagRouteLabels[route];
  if (label != null) return label;
  if (route.isFirst) return homeTab == 0 ? 'home_tab:conversations' : 'home_tab:tasks';
  final name = route.settings.name;
  if (name != null && name.startsWith('/') && !name.contains('?') && name.length <= 32) return name;
  if (route is PopupRoute) return route is ModalBottomSheetRoute ? 'sheet' : 'popup';
  return 'page';
}
