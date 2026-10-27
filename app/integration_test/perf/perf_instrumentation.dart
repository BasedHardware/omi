import 'dart:ui';
import 'dart:developer';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

class PerfInstrumentation {
  final List<FrameTiming> timings = [];
  final List<double> uiMs = [];
  final List<int> animationCallbacks = [];
  final Map<String, int> rebuilds = {};
  final Map<String, int> initialBuilds = {};
  final List<Map<String, int>> frameRebuilders = [];
  int idleFrames = 0;

  /// UI-thread time per pipeline phase (BUILD, LAYOUT, PAINT, COMPOSITING,
  /// SEMANTICS, FINALIZE TREE) over the measured window, from FlutterTimeline.
  /// Within one run the split is stable even when host wall-clock is not.
  final Map<String, double> phaseMs = {};
  final Map<String, int> phaseCounts = {};
  final List<Map<String, Object?>> images = [];
  final Map<String, int> maxLayers = {};
  int sampledFrames = 0;
  int layouts = 0;
  int paints = 0;
  bool _oldProfileLayouts = false;
  PaintImageCallback? _oldImageCallback;
  ProfilePaintCallback? _oldPaintCallback;
  bool semanticsEnabled = false;
  int _windowStart = 0;
  int? _windowEnd;
  int _buildCount = 0;
  RebuildDirtyWidgetCallback? _previous;
  bool active = false;
  int? _frameCallback;

  void _beginFrame(Duration timestamp) {
    if (!active) return;
    sampledFrames++;
    semanticsEnabled = semanticsEnabled || WidgetsBinding.instance.semanticsEnabled;
    final watch = Stopwatch()..start();
    final before = _buildCount;
    final countsBefore = Map<String, int>.of(rebuilds);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      watch.stop();
      if (active) _countLayers();
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

  void start(TestWidgetsFlutterBinding binding) {
    timings.clear();
    uiMs.clear();
    animationCallbacks.clear();
    rebuilds.clear();
    initialBuilds.clear();
    frameRebuilders.clear();
    idleFrames = 0;
    phaseMs.clear();
    phaseCounts.clear();
    images.clear();
    maxLayers.clear();
    sampledFrames = layouts = paints = 0;
    _oldProfileLayouts = debugProfileLayoutsEnabled;
    debugProfileLayoutsEnabled = true;
    _oldImageCallback = debugOnPaintImage;
    debugOnPaintImage = (info) {
      _oldImageCallback?.call(info);
      if (active) images.add(info.toJson());
    };
    _oldPaintCallback = debugOnProfilePaint;
    debugOnProfilePaint = (object) {
      _oldPaintCallback?.call(object);
      if (active) paints++;
    };
    semanticsEnabled = binding.semanticsEnabled;
    FlutterTimeline.debugCollectionEnabled = true;
    FlutterTimeline.debugReset();
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
    _collectPhases();
  }

  void _collectPhases() {
    if (!FlutterTimeline.debugCollectionEnabled) return;
    const phases = {
      'BUILD',
      'LAYOUT',
      'PAINT',
      'COMPOSITING',
      'UPDATING COMPOSITING BITS',
      'SEMANTICS',
      'FINALIZE TREE'
    };
    final blocks = FlutterTimeline.debugCollect().timedBlocks;
    for (final phase in phases) {
      final matching = blocks.where((b) => b.name == phase || b.name.startsWith('$phase ('));
      phaseMs[phase] = matching.fold<double>(0, (n, b) => n + b.duration / 1000);
      phaseCounts[phase] = matching.length;
    }
    final layoutWindows = blocks.where((b) => b.name == 'LAYOUT' || b.name.startsWith('LAYOUT (')).toList();
    layouts = blocks
        .where((b) => b.name.startsWith('Render') && layoutWindows.any((w) => b.start >= w.start && b.end <= w.end))
        .length;
    FlutterTimeline.debugCollectionEnabled = false;
  }

  void _countLayers() {
    final counts = <String, int>{};
    void visit(Layer layer) {
      final name = layer.runtimeType.toString();
      counts.update(name, (n) => n + 1, ifAbsent: () => 1);
      if (layer is ContainerLayer) {
        Layer? child = layer.firstChild;
        while (child != null) {
          visit(child);
          child = child.nextSibling;
        }
      }
    }

    for (final view in WidgetsBinding.instance.renderViews) {
      final layer = view.debugLayer;
      if (layer != null) visit(layer);
    }
    for (final entry in counts.entries) {
      if (entry.value > (maxLayers[entry.key] ?? 0)) maxLayers[entry.key] = entry.value;
    }
  }

  Map<String, num> get workCounts => {
        'rebuilds': rebuilds.values.fold<int>(0, (a, b) => a + b),
        'layouts': layouts,
        'paints': paints,
        'semantics_compiles': phaseCounts['SEMANTICS'] ?? 0,
        'max_clip_layers': maxLayers.entries.where((e) => e.key.startsWith('Clip')).fold<int>(0, (a, e) => a + e.value),
        'max_opacity_layers': maxLayers['OpacityLayer'] ?? 0,
        'max_image_pixels': images.fold<double>(0, (n, image) {
          final size = image['imageSize'] as Map<String, Object?>;
          final pixels = (size['width'] as num).toDouble() * (size['height'] as num).toDouble();
          return pixels > n ? pixels : n;
        }),
      };

  void stop(TestWidgetsFlutterBinding binding) {
    active = false;
    _collectPhases();
    binding.removeTimingsCallback(_timings);
    if (_frameCallback != null) binding.cancelFrameCallbackWithId(_frameCallback!);
    debugOnRebuildDirtyWidget = _previous;
    debugProfileLayoutsEnabled = _oldProfileLayouts;
    debugOnPaintImage = _oldImageCallback;
    debugOnProfilePaint = _oldPaintCallback;
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
