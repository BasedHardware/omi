import 'dart:ui';
import 'dart:developer';
import 'package:flutter/widgets.dart';
import 'package:integration_test/integration_test.dart';

class PerfInstrumentation {
  final List<FrameTiming> timings = [];
  final List<double> uiMs = [];
  final List<int> animationCallbacks = [];
  final Map<String, int> rebuilds = {};
  final Map<String, int> initialBuilds = {};
  final List<Map<String, int>> frameRebuilders = [];
  int idleFrames = 0;
  int _windowStart = 0;
  int? _windowEnd;
  int _buildCount = 0;
  RebuildDirtyWidgetCallback? _previous;
  bool active = false;
  int? _frameCallback;

  void _beginFrame(Duration timestamp) {
    if (!active) return;
    final watch = Stopwatch()..start();
    final before = _buildCount;
    final countsBefore = Map<String, int>.of(rebuilds);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      watch.stop();
      final callbacks = (WidgetsBinding.instance.transientCallbackCount - 1).clamp(0, 10000);
      if (_buildCount > before || callbacks > 0) {
        recordUiFrame(watch.elapsedMicroseconds / 1000, callbacks);
        if (active) {
          frameRebuilders.add({
            for (final e in rebuilds.entries)
              if (e.value > (countsBefore[e.key] ?? 0)) e.key: e.value - (countsBefore[e.key] ?? 0)
          });
        }
      } else {
        idleFrames++;
      }
    });
    _frameCallback = WidgetsBinding.instance.scheduleFrameCallback(_beginFrame);
  }

  void _timings(List<FrameTiming> batch) {
    if (active) {
      timings.addAll(batch.where((t) {
        final start = t.timestampInMicroseconds(FramePhase.vsyncStart);
        return start >= _windowStart && (_windowEnd == null || start <= _windowEnd!);
      }));
    }
  }

  void start(IntegrationTestWidgetsFlutterBinding binding) {
    timings.clear();
    uiMs.clear();
    animationCallbacks.clear();
    rebuilds.clear();
    initialBuilds.clear();
    frameRebuilders.clear();
    idleFrames = 0;
    _buildCount = 0;
    _windowStart = Timeline.now;
    _windowEnd = null;
    _previous = debugOnRebuildDirtyWidget;
    debugOnRebuildDirtyWidget = (element, builtOnce) {
      _previous?.call(element, builtOnce);
      if (active) {
        _buildCount++;
        final name = element.widget.runtimeType.toString();
        if (!builtOnce) initialBuilds.update(name, (n) => n + 1, ifAbsent: () => 1);
        rebuilds.update(name, (count) => count + 1, ifAbsent: () => 1);
      }
    };
    active = true;
    _frameCallback = binding.scheduleFrameCallback(_beginFrame);
    binding.addTimingsCallback(_timings);
  }

  void recordUiFrame(double ms, int callbacks) {
    if (!active) return;
    uiMs.add(ms);
    animationCallbacks.add(callbacks);
  }

  void endWindow() {
    _windowEnd = Timeline.now;
  }

  void stop(IntegrationTestWidgetsFlutterBinding binding) {
    active = false;
    binding.removeTimingsCallback(_timings);
    if (_frameCallback != null) binding.cancelFrameCallbackWithId(_frameCallback!);
    debugOnRebuildDirtyWidget = _previous;
  }
}

/// Nearest-rank percentiles, including tiny samples; empty samples are invalid.
double quantile(List<double> values, double q) {
  if (values.isEmpty) throw StateError('No frames recorded');
  final sorted = [...values]..sort();
  return sorted[(sorted.length * q).ceil().clamp(1, sorted.length) - 1];
}

Map<String, double> quantiles(List<double> values) => {
      for (final q in [50, 90, 95, 99]) 'p$q': quantile(values, q / 100),
    };
