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
  Future<List<Detection>> detect(LocalVisionFrame frame) async {
    if (!Platform.isAndroid) {
      throw UnsupportedError('Android YOLOE detector is only available on Android');
    }

    await _loadModelIfNeeded();

    final prefs = SharedPreferencesUtil();
    final rawDetections = await _channel.invokeListMethod<dynamic>('detectJpeg', <String, dynamic>{
      'bytes': frame.jpegBytes,
      'confidenceThreshold': 0.25,
      'iouThreshold': 0.45,
      'maxDetections': prefs.localYoloeMaxObjectsPerAnnouncement * 4,
    });

    return (rawDetections ?? const <dynamic>[])
        .whereType<Map<dynamic, dynamic>>()
        .map((raw) => _parseDetection(raw, frame))
        .whereType<Detection>()
        .toList();
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
}
