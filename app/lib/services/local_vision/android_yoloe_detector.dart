import 'dart:io';

import 'package:flutter/services.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/local_vision/local_vision_service.dart';
import 'package:omi/services/local_vision/yoloe_model_assets.dart';

class AndroidYoloeDetector implements LocalVisionDetector {
  AndroidYoloeDetector({MethodChannel? channel}) : _channel = channel ?? const MethodChannel(_channelName);

  static const _channelName = 'com.omi/local_yoloe';

  final MethodChannel _channel;
  bool _loaded = false;

  @override
  Future<LocalVisionDetectorResult> detect(LocalVisionFrame frame) async {
    if (!Platform.isAndroid) {
      throw UnsupportedError('Android YOLOE detector is only available on Android');
    }

    await _loadModelIfNeeded();

    final prefs = SharedPreferencesUtil();
    final rawResult = await _channel.invokeMethod<dynamic>('detectJpeg', <String, dynamic>{
      'bytes': frame.jpegBytes,
      'confidenceThreshold': prefs.localYoloeConfidenceThreshold,
      'iouThreshold': 0.45,
      'maxDetections': prefs.localYoloeMaxObjectsPerFrame,
    });

    final rawDetections = rawResult is Map ? rawResult['detections'] : rawResult;
    final detections = (rawDetections is List ? rawDetections : const <dynamic>[])
        .whereType<Map<dynamic, dynamic>>()
        .map((raw) => _parseDetection(raw, frame))
        .whereType<Detection>()
        .toList();
    return LocalVisionDetectorResult(
      detections: detections,
      latency: _parseLatency(rawResult),
    );
  }

  Future<void> close() async {
    if (!_loaded || !Platform.isAndroid) return;
    await _channel.invokeMethod<void>('close');
    _loaded = false;
  }

  Future<void> _loadModelIfNeeded() async {
    if (_loaded) return;
    await _channel.invokeMethod<void>('loadModel', <String, dynamic>{
      'modelDirectory': YoloeModelAssets.modelDirectory,
    });
    _loaded = true;
  }

  Detection? _parseDetection(Map<dynamic, dynamic> raw, LocalVisionFrame frame) {
    final label = raw['label'];
    final confidence = raw['confidence'];
    final box = raw['box'];

    if (label is! String || confidence is! num || box is! Map) return null;

    final left = box['left'];
    final top = box['top'];
    final width = box['width'];
    final height = box['height'];
    if (left is! num || top is! num || width is! num || height is! num) return null;

    return Detection(
      label: label,
      confidence: confidence.toDouble(),
      box: DetectionBox(
        left: left.toDouble(),
        top: top.toDouble(),
        width: width.toDouble(),
        height: height.toDouble(),
      ),
      sourceFrameId: frame.frameId,
      timestamp: frame.timestamp,
    );
  }

  LocalVisionLatencyMetrics _parseLatency(dynamic rawResult) {
    if (rawResult is! Map) return const LocalVisionLatencyMetrics();
    final latency = rawResult['latencyMs'];
    if (latency is! Map) return const LocalVisionLatencyMetrics();
    return LocalVisionLatencyMetrics(
      preprocessMs: _doubleValue(latency['preprocess']),
      inferenceMs: _doubleValue(latency['inference']),
      postprocessMs: _doubleValue(latency['postprocess']),
      nativeTotalMs: _doubleValue(latency['total']),
    );
  }

  double? _doubleValue(dynamic value) {
    return value is num ? value.toDouble() : null;
  }
}
