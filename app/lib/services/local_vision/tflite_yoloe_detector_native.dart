import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/local_vision/local_vision_service.dart';
import 'package:omi/services/local_vision/yoloe_model_assets.dart';

class TfliteYoloeDetector implements LocalVisionDetector {
  TfliteYoloeDetector();

  static const int _inputSize = 640;
  static const int _boxCoordinateCount = 4;

  Interpreter? _interpreter;
  List<String>? _labels;
  Set<String>? _physicalObjectLabels;

  @override
  Future<LocalVisionDetectorResult> detect(LocalVisionFrame frame) async {
    await _loadIfNeeded();

    final totalStartedAt = DateTime.now();
    final preprocessStartedAt = DateTime.now();
    final decoded = img.decodeJpg(frame.jpegBytes) ?? img.decodeImage(frame.jpegBytes);
    if (decoded == null) {
      throw StateError('Failed to decode local vision JPEG frame');
    }
    final letterbox = _letterbox(decoded);
    final preprocessMs = _elapsedMs(preprocessStartedAt);

    final inferenceStartedAt = DateTime.now();
    final outputTensors = _interpreter!.getOutputTensors();
    final outputs = <int, Object>{
      for (var index = 0; index < outputTensors.length; index++) index: _zeroTensor(outputTensors[index].shape),
    };
    _interpreter!.runForMultipleInputs([letterbox.input], outputs);
    final inferenceMs = _elapsedMs(inferenceStartedAt);

    final postprocessStartedAt = DateTime.now();
    final prefs = SharedPreferencesUtil();
    final detections = _parseOutputs(
      outputs: outputs.values.toList(growable: false),
      labels: _labels!,
      physicalObjectLabels: _physicalObjectLabels!,
      frame: frame,
      originalWidth: decoded.width,
      originalHeight: decoded.height,
      scale: letterbox.scale,
      padX: letterbox.padX,
      padY: letterbox.padY,
      confidenceThreshold: prefs.localYoloeConfidenceThreshold,
      iouThreshold: 0.45,
      maxDetections: prefs.localYoloeMaxObjectsPerFrame,
    );
    outputs.clear();
    final postprocessMs = _elapsedMs(postprocessStartedAt);

    return LocalVisionDetectorResult(
      detections: detections,
      latency: LocalVisionLatencyMetrics(
        preprocessMs: preprocessMs,
        inferenceMs: inferenceMs,
        postprocessMs: postprocessMs,
        nativeTotalMs: _elapsedMs(totalStartedAt),
      ),
    );
  }

  Future<void> close() async {
    _interpreter?.close();
    _interpreter = null;
  }

  Future<void> _loadIfNeeded() async {
    if (_interpreter != null && _labels != null && _physicalObjectLabels != null) return;
    _interpreter = await Interpreter.fromAsset(
      YoloeModelAssets.modelPath,
      options: InterpreterOptions()..threads = 2,
    );
    _labels = await _loadLabels();
    _physicalObjectLabels = await _loadPhysicalObjectLabels();
  }

  Future<List<String>> _loadLabels() async {
    final raw = await rootBundle.loadString(YoloeModelAssets.labelsPath);
    final json = jsonDecode(raw) as Map<String, dynamic>;
    final labels = json['labels'];
    if (labels is! List) return const [];
    return labels.map((entry) {
      if (entry is Map && entry['name'] is String) return entry['name'] as String;
      return '';
    }).toList(growable: false);
  }

  Future<Set<String>> _loadPhysicalObjectLabels() async {
    final raw = await rootBundle.loadString(YoloeModelAssets.physicalObjectTagsPath);
    return raw
        .split('\n')
        .map((line) => line.trim().toLowerCase())
        .where((label) => label.isNotEmpty && !label.startsWith('#'))
        .toSet();
  }

  _LetterboxInput _letterbox(img.Image source) {
    final scale = math.min(_inputSize / source.width, _inputSize / source.height);
    final resizedWidth = math.max(1, (source.width * scale).round());
    final resizedHeight = math.max(1, (source.height * scale).round());
    final padX = (_inputSize - resizedWidth) / 2.0;
    final padY = (_inputSize - resizedHeight) / 2.0;

    final resized =
        img.copyResize(source, width: resizedWidth, height: resizedHeight, interpolation: img.Interpolation.linear);
    final input = List.generate(
      1,
      (_) => List.generate(
        _inputSize,
        (y) => List.generate(_inputSize, (x) {
          final sourceX = x - padX.round();
          final sourceY = y - padY.round();
          if (sourceX < 0 || sourceY < 0 || sourceX >= resizedWidth || sourceY >= resizedHeight) {
            return <double>[114 / 255.0, 114 / 255.0, 114 / 255.0];
          }
          final pixel = resized.getPixel(sourceX, sourceY);
          return <double>[pixel.r / 255.0, pixel.g / 255.0, pixel.b / 255.0];
        }),
      ),
    );

    return _LetterboxInput(input: input, scale: scale, padX: padX, padY: padY);
  }

  Object _zeroTensor(List<int> shape) {
    if (shape.isEmpty) return 0.0;
    final dimension = shape.first;
    if (dimension <= 0) return <Object>[];
    if (shape.length == 1) return List<double>.filled(dimension, 0);
    return List.generate(dimension, (_) => _zeroTensor(shape.sublist(1)), growable: false);
  }

  List<Detection> _parseOutputs({
    required List<Object> outputs,
    required List<String> labels,
    required Set<String> physicalObjectLabels,
    required LocalVisionFrame frame,
    required int originalWidth,
    required int originalHeight,
    required double scale,
    required double padX,
    required double padY,
    required double confidenceThreshold,
    required double iouThreshold,
    required int maxDetections,
  }) {
    final candidates = <Detection>[];

    for (final output in outputs) {
      final shape = _tensorShape(output);
      if (shape.length < 2 || shape.length > 3) continue;
      final rows = _candidateRows(output, shape, labels.length);
      if (rows.isEmpty) continue;

      candidates.addAll(
        _parseRows(
          rows: rows,
          labels: labels,
          physicalObjectLabels: physicalObjectLabels,
          frame: frame,
          originalWidth: originalWidth,
          originalHeight: originalHeight,
          scale: scale,
          padX: padX,
          padY: padY,
          confidenceThreshold: confidenceThreshold,
        ),
      );
    }

    candidates.sort((a, b) => b.confidence.compareTo(a.confidence));
    final kept = <Detection>[];
    for (final detection in candidates) {
      final suppressed = kept.any(
        (prior) => detection.label == prior.label && detection.box.intersectionOverUnion(prior.box) > iouThreshold,
      );
      if (!suppressed) kept.add(detection);
      if (kept.length >= maxDetections) break;
    }
    return kept;
  }

  List<List<double>> _candidateRows(Object output, List<int> shape, int labelCount) {
    final rankAdjusted = shape.length == 3 && shape.first == 1 ? (output as List).first : output;
    final rankAdjustedShape = shape.length == 3 && shape.first == 1 ? shape.sublist(1) : shape;
    if (rankAdjustedShape.length != 2 || rankAdjusted is! List || rankAdjusted.isEmpty) return const [];

    final height = rankAdjustedShape[0];
    final width = rankAdjustedShape[1];

    if (_looksLikeRows(height, width, labelCount)) {
      return rankAdjusted.map((row) => _toDoubleList(row)).where((row) => row.length >= 6).toList(growable: false);
    }

    if (_looksLikeRows(width, height, labelCount)) {
      return _transposeRows(rankAdjusted, rowCount: width, valueCount: height);
    }

    return const [];
  }

  bool _looksLikeRows(int rowCount, int valueCount, int labelCount) {
    if (rowCount <= 0 || valueCount < 6) return false;
    if (valueCount <= 512) return true;
    return valueCount == labelCount + _boxCoordinateCount || valueCount == labelCount + _boxCoordinateCount + 1;
  }

  List<List<double>> _transposeRows(List source, {required int rowCount, required int valueCount}) {
    final rows = <List<double>>[];
    for (var rowIndex = 0; rowIndex < rowCount; rowIndex++) {
      final row = List<double>.filled(valueCount, 0);
      for (var valueIndex = 0; valueIndex < valueCount; valueIndex++) {
        final values = source[valueIndex];
        if (values is List && rowIndex < values.length) row[valueIndex] = _toDouble(values[rowIndex]);
      }
      rows.add(row);
    }
    return rows;
  }

  List<Detection> _parseRows({
    required List<List<double>> rows,
    required List<String> labels,
    required Set<String> physicalObjectLabels,
    required LocalVisionFrame frame,
    required int originalWidth,
    required int originalHeight,
    required double scale,
    required double padX,
    required double padY,
    required double confidenceThreshold,
  }) {
    final candidates = <Detection>[];
    for (final row in rows) {
      if (row.length < 6) continue;
      final parsedClass = _parseClassScore(row, labels.length);
      if (parsedClass == null) continue;
      final score = parsedClass.score;
      if (score < confidenceThreshold || score.isNaN) continue;
      final classId = parsedClass.classId;
      if (classId < 0 || classId >= labels.length) continue;
      final label = labels[classId];
      if (!physicalObjectLabels.contains(label.trim().toLowerCase())) continue;

      var x0 = row[0];
      var y0 = row[1];
      var x1 = row[2];
      var y1 = row[3];
      if (x1 < x0 || y1 < y0) {
        final cx = row[0];
        final cy = row[1];
        final w = row[2].abs();
        final h = row[3].abs();
        x0 = cx - w / 2;
        y0 = cy - h / 2;
        x1 = cx + w / 2;
        y1 = cy + h / 2;
      }

      final left = ((x0 - padX) / scale).clamp(0.0, originalWidth.toDouble());
      final top = ((y0 - padY) / scale).clamp(0.0, originalHeight.toDouble());
      final right = ((x1 - padX) / scale).clamp(0.0, originalWidth.toDouble());
      final bottom = ((y1 - padY) / scale).clamp(0.0, originalHeight.toDouble());
      final width = (right - left).clamp(0.0, originalWidth.toDouble());
      final height = (bottom - top).clamp(0.0, originalHeight.toDouble());
      if (width <= 0 || height <= 0) continue;

      candidates.add(
        Detection(
          label: label,
          confidence: score,
          box: DetectionBox(
            left: left / originalWidth,
            top: top / originalHeight,
            width: width / originalWidth,
            height: height / originalHeight,
          ),
          sourceFrameId: frame.frameId,
          timestamp: frame.timestamp,
        ),
      );
    }
    return candidates;
  }

  _ClassScore? _parseClassScore(List<double> row, int labelCount) {
    final directClassId = row[5].round();
    if (row.length < labelCount + _boxCoordinateCount && directClassId >= 0 && directClassId < labelCount) {
      return _ClassScore(classId: directClassId, score: row[4]);
    }

    final classStart = row.length == labelCount + _boxCoordinateCount + 1 ? 5 : 4;
    if (row.length <= classStart) return null;
    var bestClassId = -1;
    var bestScore = double.negativeInfinity;
    final availableClassCount = math.min(labelCount, row.length - classStart);
    for (var classOffset = 0; classOffset < availableClassCount; classOffset++) {
      final rawScore = row[classStart + classOffset];
      final score = rawScore >= 0 && rawScore <= 1 ? rawScore : 1 / (1 + math.exp(-rawScore));
      if (score > bestScore) {
        bestScore = score;
        bestClassId = classOffset;
      }
    }
    if (bestClassId < 0) return null;

    final objectness = classStart == 5 ? row[4] : 1.0;
    final normalizedObjectness = objectness >= 0 && objectness <= 1 ? objectness : 1 / (1 + math.exp(-objectness));
    return _ClassScore(classId: bestClassId, score: bestScore * normalizedObjectness);
  }

  List<int> _tensorShape(Object tensor) {
    final shape = <int>[];
    Object? current = tensor;
    while (current is List) {
      shape.add(current.length);
      current = current.isEmpty ? null : current.first;
    }
    return shape;
  }

  List<double> _toDoubleList(Object? value) {
    if (value is! List) return const [];
    return value.map(_toDouble).toList(growable: false);
  }

  double _toDouble(Object? value) {
    if (value is num) return value.toDouble();
    return 0;
  }

  double _elapsedMs(DateTime startedAt) {
    return DateTime.now().difference(startedAt).inMicroseconds / 1000.0;
  }
}

class _LetterboxInput {
  const _LetterboxInput({required this.input, required this.scale, required this.padX, required this.padY});

  final List<List<List<List<double>>>> input;
  final double scale;
  final double padX;
  final double padY;
}

class _ClassScore {
  const _ClassScore({required this.classId, required this.score});

  final int classId;
  final double score;
}
